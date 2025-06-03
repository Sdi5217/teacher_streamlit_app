import streamlit as st
import sqlite3
import os
import shutil
from PIL import Image # นำเข้า Pillow เพื่อจัดการรูปภาพ

# --- Configuration (ตั้งค่าพื้นฐาน) ---
DATABASE_NAME = 'teacher_management.db'
PHOTO_DIR = 'teacher_photos'
UPLOAD_FOLDER = PHOTO_DIR # โฟลเดอร์สำหรับเก็บรูปภาพที่ผู้ใช้อัปโหลด

# --- Database Setup and Functions (ฟังก์ชันจัดการฐานข้อมูล) ---

def get_db_connection():
    """
    พยายามเชื่อมต่อฐานข้อมูลโดยใช้ st.connection สำหรับ Streamlit Cloud หากมีการตั้งค่าไว้
    หากไม่สามารถเชื่อมต่อได้ (เช่น รันในเครื่อง local หรือไม่ได้ตั้งค่าบน Cloud)
    จะ fallback ไปใช้ sqlite3.connect โดยตรง
    """
    try:
        # ตรวจสอบว่ามี secret สำหรับ connection ชื่อ 'teacher_db' หรือไม่
        if "connections" in st.secrets and "teacher_db" in st.secrets["connections"]:
            return st.connection('teacher_db', type='sql')
    except Exception:
        # หากเกิดข้อผิดพลาดในการใช้ st.connection (เช่น ไม่ได้กำหนดใน secrets) ให้ดำเนินการต่อ
        pass

    # Fallback: เชื่อมต่อฐานข้อมูล SQLite โดยตรง (เหมาะสำหรับการรัน local)
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row # ทำให้สามารถเรียกข้อมูลด้วยชื่อคอลัมน์ได้
    return conn

def setup_database():
    """
    ตั้งค่าตาราง 'teachers' ในฐานข้อมูลหากยังไม่มี และสร้างโฟลเดอร์สำหรับเก็บรูปภาพ.
    รองรับทั้งการเชื่อมต่อผ่าน Streamlit และ sqlite3 โดยตรง
    """
    conn = get_db_connection()
    
    # ตรวจสอบว่าวัตถุ 'conn' มี attribute 'session' หรือไม่ (บ่งชี้ว่าเป็น Streamlit Connection object)
    if hasattr(conn, 'session'):
        with conn.session as s:
            s.execute('''
                CREATE TABLE IF NOT EXISTS teachers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    school_affiliation TEXT,
                    major_subject TEXT,
                    teaching_subjects TEXT,
                    contact_number TEXT,
                    photo_path TEXT
                )
            ''')
            s.commit()
        # ไม่จำเป็นต้องปิดการเชื่อมต่อหากเป็น Streamlit Connection object เนื่องจาก Streamlit จัดการให้
    else: # เป็นการเชื่อมต่อ sqlite3 โดยตรง
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                school_affiliation TEXT,
                major_subject TEXT,
                teaching_subjects TEXT,
                contact_number TEXT,
                photo_path TEXT
            )
        ''')
        conn.commit()
        conn.close() # ปิดการเชื่อมต่อโดยตรงหลังจากตั้งค่าเสร็จ

    # สร้างโฟลเดอร์สำหรับเก็บรูปภาพ หากยังไม่มี
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        # st.info(f"Created upload directory: {UPLOAD_FOLDER}") # สามารถคอมเมนต์ออกได้เมื่อใช้งานจริง

# ใช้ st.cache_data เพื่อ cache ผลลัพธ์จากการดึงข้อมูลจากฐานข้อมูลเพื่อประสิทธิภาพ
@st.cache_data(ttl=3600) # Cache ข้อมูลเป็นเวลา 1 ชั่วโมง
def get_all_teachers_from_db_cached():
    """ดึงข้อมูลครูทั้งหมดจากฐานข้อมูลและทำการแคช"""
    conn = get_db_connection()
    if hasattr(conn, 'session'): # หากเป็นการเชื่อมต่อ Streamlit SQL
        df = conn.query('SELECT * FROM teachers', ttl=0) # ttl=0 หมายถึงไม่แคชที่ระดับ query
        return df.to_dict(orient='records') # แปลง DataFrame เป็น list ของ dicts เพื่อให้รูปแบบข้อมูลสอดคล้องกัน
    else: # หากเป็นการเชื่อมต่อ sqlite3 โดยตรง
        cursor = conn.cursor()
        teachers = cursor.execute('SELECT * FROM teachers').fetchall()
        conn.close()
        return [dict(t) for t in teachers] # แปลง sqlite3.Row เป็น dict

def get_teacher_by_id_from_db(teacher_id):
    """ดึงข้อมูลครูหนึ่งคนตาม ID"""
    conn = get_db_connection()
    if hasattr(conn, 'session'): # หากเป็นการเชื่อมต่อ Streamlit SQL
        try:
            teacher = conn.query(f'SELECT * FROM teachers WHERE id = {teacher_id}', ttl=0).iloc[0].to_dict()
            return teacher
        except IndexError: # จัดการกรณีที่ไม่พบครู
            return None
    else: # หากเป็นการเชื่อมต่อ sqlite3 โดยตรง
        cursor = conn.cursor()
        teacher = cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,)).fetchone()
        conn.close()
        return dict(teacher) if teacher else None

def add_teacher_to_db(full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None):
    """เพิ่มข้อมูลครูใหม่ลงในฐานข้อมูล รวมถึงบันทึกไฟล์รูปภาพหากมี"""
    conn = get_db_connection()
    saved_photo_path = None
    if photo_file:
        try:
            extension = os.path.splitext(photo_file.name)[1]
            # สร้างชื่อไฟล์ที่ไม่ซ้ำกันเพื่อหลีกเลี่ยงการเขียนทับ
            new_filename = f"{os.path.splitext(photo_file.name)[0]}_{os.urandom(8).hex()}{extension}"
            saved_photo_path_full = os.path.join(UPLOAD_FOLDER, new_filename)
            
            # บันทึกไฟล์ที่อัปโหลด
            with open(saved_photo_path_full, "wb") as f:
                f.write(photo_file.getbuffer())
            saved_photo_path = new_filename # เก็บเฉพาะชื่อไฟล์ที่สัมพันธ์กับ PHOTO_DIR
            st.toast(f"บันทึกรูปภาพ: {saved_photo_path_full}", icon="📸")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพ: {e}")
            saved_photo_path = None

    if hasattr(conn, 'session'): # หากเป็นการเชื่อมต่อ Streamlit SQL
        with conn.session as s:
            s.execute('''
                INSERT INTO teachers (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_path)
                VALUES (:full_name, :school_affiliation, :major_subject, :teaching_subjects, :contact_number, :photo_path)
            ''', params=dict(
                full_name=full_name,
                school_affiliation=school_affiliation,
                major_subject=major_subject,
                teaching_subjects=teaching_subjects,
                contact_number=contact_number,
                photo_path=saved_photo_path
            ))
            s.commit()
    else: # หากเป็นการเชื่อมต่อ sqlite3 โดยตรง
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO teachers (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_path)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, saved_photo_path))
        conn.commit()
        conn.close()
    st.cache_data.clear() # ล้างแคชหลังจากแก้ไขข้อมูล เพื่อให้มั่นใจว่าข้อมูลสดใหม่ในการดึงครั้งต่อไป
    st.success(f"เพิ่มข้อมูลครู '{full_name}' สำเร็จ!")

def update_teacher_in_db(teacher_id, full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None):
    """
    อัปเดตข้อมูลครูที่มีอยู่แล้วในฐานข้อมูล.
    จัดการกับการอัปเดตรูปภาพ (เพิ่มใหม่, แทนที่ของเก่า, หรือล้างรูปภาพ).
    """
    conn = get_db_connection()
    current_teacher = get_teacher_by_id_from_db(teacher_id) # ดึงข้อมูลปัจจุบันเพื่อเปรียบเทียบและหา path รูปเก่า

    if not current_teacher:
        st.error("ไม่พบครูที่ต้องการแก้ไข")
        return False

    updates = []
    params = {}

    # เพิ่มข้อมูลลงใน updates เฉพาะเมื่อค่ามีการเปลี่ยนแปลงเท่านั้น
    if full_name is not None and full_name != current_teacher['full_name']:
        updates.append("full_name = :full_name")
        params['full_name'] = full_name
    if school_affiliation is not None and school_affiliation != current_teacher['school_affiliation']:
        updates.append("school_affiliation = :school_affiliation")
        params['school_affiliation'] = school_affiliation
    if major_subject is not None and major_subject != current_teacher['major_subject']:
        updates.append("major_subject = :major_subject")
        params['major_subject'] = major_subject
    if teaching_subjects is not None and teaching_subjects != current_teacher['teaching_subjects']:
        updates.append("teaching_subjects = :teaching_subjects")
        params['teaching_subjects'] = teaching_subjects
    if contact_number is not None and contact_number != current_teacher['contact_number']:
        updates.append("contact_number = :contact_number")
        params['contact_number'] = contact_number
    
    # จัดการการอัปเดตรูปภาพ
    if photo_file: # มีไฟล์ใหม่ถูกอัปโหลด
        if current_teacher and current_teacher['photo_path']: # ลบรูปภาพเก่าหากมี
            old_photo_full_path = os.path.join(UPLOAD_FOLDER, current_teacher['photo_path'])
            if os.path.exists(old_photo_full_path):
                try:
                    os.remove(old_photo_full_path)
                    st.info(f"ลบรูปภาพเก่า: {old_photo_full_path}")
                except Exception as e:
                    st.warning(f"เกิดข้อผิดพลาดในการลบรูปภาพเก่า: {e}")
        try:
            extension = os.path.splitext(photo_file.name)[1]
            new_filename = f"{os.path.splitext(photo_file.name)[0]}_{os.urandom(8).hex()}{extension}"
            saved_photo_path_full = os.path.join(UPLOAD_FOLDER, new_filename)
            with open(saved_photo_path_full, "wb") as f:
                f.write(photo_file.getbuffer())
            saved_photo_path = new_filename # เก็บเฉพาะชื่อไฟล์ที่สัมพันธ์กับ PHOTO_DIR
            updates.append("photo_path = :photo_path")
            params['photo_path'] = saved_photo_path
            st.toast(f"บันทึกรูปภาพใหม่: {saved_photo_path_full}", icon="📸")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพใหม่: {e}")
            
    elif st.session_state.get('photo_cleared', False): # ผู้ใช้เลือก "ลบรูปภาพปัจจุบัน"
        if current_teacher and current_teacher['photo_path']: # ลบไฟล์รูปภาพปัจจุบัน
            old_photo_full_path = os.path.join(UPLOAD_FOLDER, current_teacher['photo_path'])
            if os.path.exists(old_photo_full_path):
                try:
                    os.remove(old_photo_full_path)
                    st.info(f"ลบรูปภาพ (ตามคำสั่ง): {old_photo_full_path}")
                except Exception as e:
                    st.warning(f"เกิดข้อผิดพลาดในการลบรูปภาพ (ตามคำสั่ง): {e}")
        updates.append("photo_path = :photo_path")
        params['photo_path'] = None # ตั้งค่าเป็น NULL ใน DB

    if not updates: # หากไม่มีข้อมูลที่เปลี่ยนแปลงเลย
        st.info("ไม่มีข้อมูลที่เปลี่ยนแปลง")
        return False

    params['id'] = teacher_id
    query = f"UPDATE teachers SET {', '.join(updates)} WHERE id = :id"
    
    if hasattr(conn, 'session'): # หากเป็นการเชื่อมต่อ Streamlit SQL
        with conn.session as s:
            s.execute(query, params=params)
            s.commit()
    else: # หากเป็นการเชื่อมต่อ sqlite3 โดยตรง (ไม่ค่อยแข็งแรงสำหรับการอัปเดตแบบไดนามิก)
        cursor = conn.cursor()
        # สำหรับ sqlite3 โดยตรง การจัดการพารามิเตอร์แบบไดนามิกจะซับซ้อน
        # ขอแนะนำให้ใช้ st.connection สำหรับการทำงานฐานข้อมูลใน Streamlit
        st.error("การอัปเดตข้อมูลผ่าน SQLite โดยตรงไม่รองรับการอัปเดตแบบไดนามิกหลายฟิลด์อย่างสมบูรณ์ด้วยวิธีการนี้")
        conn.close() # ปิดการเชื่อมต่อโดยตรง
        return False
    st.cache_data.clear() # ล้างแคชหลังจากแก้ไขข้อมูล
    st.success(f"ข้อมูลครู ID {teacher_id} อัปเดตสำเร็จ!")
    return True

def delete_teacher_from_db(teacher_id):
    """ลบข้อมูลครูและไฟล์รูปภาพที่เกี่ยวข้องออกจากฐานข้อมูลและดิสก์"""
    conn = get_db_connection()
    teacher_to_delete = get_teacher_by_id_from_db(teacher_id) # ดึงข้อมูลเพื่อหา path รูปภาพ

    if not teacher_to_delete:
        st.error(f"ไม่พบครู ID {teacher_id} ที่ต้องการลบ")
        return False

    if hasattr(conn, 'session'): # หากเป็นการเชื่อมต่อ Streamlit SQL
        with conn.session as s:
            s.execute('DELETE FROM teachers WHERE id = :id', params=dict(id=teacher_id))
            s.commit()
    else: # หากเป็นการเชื่อมต่อ sqlite3 โดยตรง
        cursor = conn.cursor()
        cursor.execute('DELETE FROM teachers WHERE id = ?', (teacher_id,))
        conn.commit()
        conn.close()

    if teacher_to_delete and teacher_to_delete['photo_path']: # ลบไฟล์รูปภาพหากมี
        photo_full_path = os.path.join(UPLOAD_FOLDER, teacher_to_delete['photo_path'])
        if os.path.exists(photo_full_path):
            try:
                os.remove(photo_full_path)
                st.info(f"ลบรูปภาพ: {photo_full_path}")
            except Exception as e:
                st.warning(f"เกิดข้อผิดพลาดในการลบไฟล์รูปภาพ: {e}")
    st.cache_data.clear() # ล้างแคชหลังจากแก้ไขข้อมูล
    st.success(f"ข้อมูลครู ID {teacher_id} ถูกลบสำเร็จ!")
    return True

# --- Streamlit App UI (ส่วนประกอบ UI ของแอปพลิเคชัน) ---

# กำหนดการตั้งค่าหน้าเว็บ: layout, ชื่อแท็บ, และไอคอนแท็บ
st.set_page_config(
    layout="wide", # ทำให้หน้าเว็บขยายเต็มความกว้าง
    page_title="ระบบจัดการฐานข้อมูลครูกลุ่มโรงเรียนบ้านด่าน 2", # ชื่อที่แสดงบนแท็บเบราว์เซอร์
    page_icon="🏫"  # ใช้อีโมจิเป็นไอคอนแท็บ (สามารถเปลี่ยนเป็น URL ของรูปภาพได้หากต้องการ)
)

st.title("👨‍🏫 ระบบจัดการฐานข้อมูลครูกลุ่มโรงเรียนบ้านด่าน 2")

# --- เพิ่ม Logo ของกลุ่มโรงเรียน ---
logo_path = "ban_dan_2_logo.png"  # **เปลี่ยน path นี้เป็น path ที่ถูกต้องของไฟล์โลโก้ของคุณ**
                                 # (เช่น 'images/ban_dan_2_logo.png' ถ้าเก็บในโฟลเดอร์ images)
if os.path.exists(logo_path):
    try:
        logo = Image.open(logo_path)
        st.image(logo, width=150) # ปรับขนาด logo ตามต้องการ
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการโหลดโลโก้: {e}")
else:
    st.warning(f"ไม่พบไฟล์โลโก้ที่: {logo_path}")

st.markdown("---") # เส้นคั่นแนวนอน

# กำหนดสถานะเริ่มต้นของ Session สำหรับการนำทางและ ID ครูที่กำลังแก้ไข
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'list' # มุมมองเริ่มต้น: 'list', 'add', 'edit'
if 'edit_teacher_id' not in st.session_state:
    st.session_state.edit_teacher_id = None
if 'photo_cleared' not in st.session_state: # สถานะสำหรับติดตามว่าผู้ใช้ต้องการล้างรูปภาพหรือไม่
    st.session_state.photo_cleared = False

# ตั้งค่าฐานข้อมูลและโฟลเดอร์รูปภาพเมื่อเริ่มต้นแอป
setup_database()

# --- Navigation Buttons (ปุ่มนำทาง) ---
col1, col2, _ = st.columns([1,1,4]) # แบ่งคอลัมน์เพื่อจัดวางปุ่ม (ใช้ _ สำหรับคอลัมน์ที่ไม่ได้ใช้งาน)
with col1:
    if st.button("แสดงข้อมูลครูทั้งหมด", key="show_all", use_container_width=True):
        st.session_state.current_view = 'list'
        st.session_state.edit_teacher_id = None
        st.session_state.photo_cleared = False
        st.rerun() # รันแอปใหม่เพื่อเปลี่ยนมุมมองทันที
with col2:
    if st.button("เพิ่มข้อมูลครูใหม่", key="add_new", use_container_width=True):
        st.session_state.current_view = 'add'
        st.session_state.edit_teacher_id = None
        st.session_state.photo_cleared = False
        st.rerun() # รันแอปใหม่เพื่อเปลี่ยนมุมมองทันที

st.markdown("---") # เส้นคั่นแนวนอน

# --- Content Area (ส่วนเนื้อหาตามมุมมองปัจจุบัน) ---
if st.session_state.current_view == 'list':
    st.header("รายการข้อมูลครู")
    teachers = get_all_teachers_from_db_cached()

    if teachers:
        # แสดงข้อมูลครูโดยใช้คอลัมน์เพื่อการจัดวางที่ดีขึ้นสำหรับแต่ละรายการ
        for teacher in teachers:
            col_left, col_right = st.columns([2, 1])
            with col_left:
                st.subheader(f"{teacher['full_name']} (ID: {teacher['id']})")
                st.markdown(f"**สังกัดโรงเรียน:** {teacher['school_affiliation'] or '-'}")
                st.markdown(f"**วิชาเอก:** {teacher['major_subject'] or '-'}")
                st.markdown(f"**สอนรายวิชา:** {teacher['teaching_subjects'] or '-'}")
                st.markdown(f"**เบอร์ติดต่อ:** {teacher['contact_number'] or '-'}")
            with col_right:
                if teacher['photo_path']:
                    photo_path_full = os.path.join(UPLOAD_FOLDER, teacher['photo_path'])
                    if os.path.exists(photo_path_full): # ตรวจสอบว่าไฟล์รูปภาพมีอยู่จริงบนดิสก์
                        st.image(photo_path_full, caption=f"รูป {teacher['full_name']}", width=150)
                    else:
                        st.warning("ไม่พบไฟล์รูปภาพ") # แจ้งเตือนหาก path มีใน DB แต่ไฟล์ไม่มี
                else:
                    st.info("ไม่มีรูปภาพ")
                
                # ปุ่มดำเนินการสำหรับครูแต่ละคน โดยใช้ key ที่ไม่ซ้ำกัน
                edit_button = st.button(f"แก้ไข ID {teacher['id']}", key=f"edit_teacher_{teacher['id']}", use_container_width=True)
                delete_button = st.button(f"ลบ ID {teacher['id']}", key=f"delete_teacher_{teacher['id']}", use_container_width=True)
                
                if edit_button:
                    st.session_state.current_view = 'edit'
                    st.session_state.edit_teacher_id = teacher['id']
                    st.rerun()
                
                if delete_button:
                    # ใช้ session state เพื่อสร้างการยืนยันแบบง่ายๆ
                    if st.session_state.get(f'confirm_delete_{teacher["id"]}', False):
                        if delete_teacher_from_db(teacher['id']):
                            st.session_state.current_view = 'list'
                        del st.session_state[f'confirm_delete_{teacher["id"]}'] # ล้างสถานะการยืนยัน
                        st.rerun()
                    else:
                        st.session_state[f'confirm_delete_{teacher["id"]}'] = True
                        st.warning(f"คลิก 'ลบ ID {teacher['id']}' อีกครั้งเพื่อยืนยันการลบ '{teacher['full_name']}'")

            st.markdown("---") # เส้นคั่นสำหรับแต่ละรายการครู

    else:
        st.info("ไม่พบข้อมูลครูในระบบ")

elif st.session_state.current_view == 'add':
    st.header("เพิ่มข้อมูลครูใหม่")
    with st.form("add_teacher_form", clear_on_submit=True):
        full_name = st.text_input("ชื่อ-สกุล:", key="add_full_name")
        school_affiliation = st.text_input("สังกัดโรงเรียน:", key="add_school_affiliation")
        major_subject = st.text_input("วิชาเอก:", key="add_major_subject")
        teaching_subjects = st.text_input("สอนรายวิชา (คั่นด้วยคอมม่า):", key="add_teaching_subjects")
        contact_number = st.text_input("เบอร์ติดต่อ:", key="add_contact_number")
        photo_file = st.file_uploader("รูปถ่ายใบหน้า:", type=["png", "jpg", "jpeg"], key="add_photo_uploader")

        submitted = st.form_submit_button("บันทึกข้อมูลครู")
        if submitted:
            if full_name:
                add_teacher_to_db(full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file)
                st.session_state.current_view = 'list' # หลังจากเพิ่มสำเร็จ กลับไปที่มุมมองรายการ
                st.rerun()
            else:
                st.error("ชื่อ-สกุล ต้องไม่ว่างเปล่า!")

elif st.session_state.current_view == 'edit':
    teacher_id_to_edit = st.session_state.edit_teacher_id
    if teacher_id_to_edit:
        teacher_data = get_teacher_by_id_from_db(teacher_id_to_edit)
        if teacher_data:
            st.header(f"แก้ไขข้อมูลครู: {teacher_data['full_name']}")
            with st.form("edit_teacher_form"):
                # ใช้ข้อมูลปัจจุบันเป็นค่าเริ่มต้นสำหรับ input text
                new_full_name = st.text_input("ชื่อ-สกุล:", value=teacher_data['full_name'], key="edit_full_name")
                new_school_affiliation = st.text_input("สังกัดโรงเรียน:", value=teacher_data['school_affiliation'] or "", key="edit_school_affiliation")
                new_major_subject = st.text_input("วิชาเอก:", value=teacher_data['major_subject'] or "", key="edit_major_subject")
                new_teaching_subjects = st.text_input("สอนรายวิชา (คั่นด้วยคอมม่า):", value=teacher_data['teaching_subjects'] or "", key="edit_teaching_subjects")
                new_contact_number = st.text_input("เบอร์ติดต่อ:", value=teacher_data['contact_number'] or "", key="edit_contact_number")

                # แสดงรูปภาพปัจจุบันหากมี
                if teacher_data['photo_path']:
                    photo_path_full = os.path.join(UPLOAD_FOLDER, teacher_data['photo_path'])
                    if os.path.exists(photo_path_full):
                        st.image(photo_path_full, caption="รูปภาพปัจจุบัน", width=150)
                    else:
                        st.warning("ไม่พบไฟล์รูปภาพปัจจุบันในโฟลเดอร์")
                else:
                    st.info("ยังไม่มีรูปภาพสำหรับครูคนนี้")

                new_photo_file = st.file_uploader("เปลี่ยนรูปถ่ายใบหน้า (เลือกไฟล์ใหม่):", type=["png", "jpg", "jpeg"], key="edit_photo_uploader")
                
                # Checkbox สำหรับล้างรูปภาพ. รีเซ็ตสถานะ photo_cleared เมื่อฟอร์มถูกเรนเดอร์ใหม่หากไม่ได้เลือกไว้อย่างชัดเจน
                clear_photo = st.checkbox("ลบรูปภาพปัจจุบัน", value=st.session_state.get('photo_cleared', False), key="clear_current_photo")
                st.session_state.photo_cleared = clear_photo # อัปเดต session state ตามค่าของ checkbox

                submitted = st.form_submit_button("บันทึกการแก้ไข")
                if submitted:
                    if not new_full_name:
                        st.error("ชื่อ-สกุล ต้องไม่ว่างเปล่า!")
                    else:
                        # กำหนดว่าการดำเนินการกับรูปภาพจะเป็นอย่างไร
                        photo_to_save = new_photo_file # ค่าเริ่มต้น: ใช้ไฟล์ที่อัปโหลดใหม่
                        if st.session_state.photo_cleared:
                            photo_to_save = None # สัญญาณให้ลบรูปภาพหาก checkbox ถูกเลือก

                        if update_teacher_in_db( # เรียกฟังก์ชันอัปเดตข้อมูล
                            teacher_id_to_edit,
                            new_full_name,
                            new_school_affiliation,
                            new_major_subject,
                            new_teaching_subjects,
                            new_contact_number,
                            photo_to_save
                        ):
                            st.session_state.current_view = 'list'
                            st.session_state.edit_teacher_id = None
                            st.session_state.photo_cleared = False # รีเซ็ตสถานะหลังจากอัปเดต
                            st.rerun()
        else:
            st.error("ไม่พบข้อมูลครูที่ต้องการแก้ไข")
            st.session_state.current_view = 'list' # เปลี่ยนไปที่มุมมองรายการ
            st.rerun()
