import streamlit as st
import sqlite3
import os
import shutil
from PIL import Image

# --- Configuration ---
DATABASE_NAME = 'teacher_management.db'
PHOTO_DIR = 'teacher_photos'
UPLOAD_FOLDER = PHOTO_DIR 

# --- Database Setup and Functions (ส่วนนี้ไม่มีการเปลี่ยนแปลง) ---
def get_db_connection():
    try:
        if "connections" in st.secrets and "teacher_db" in st.secrets["connections"]:
            return st.connection('teacher_db', type='sql')
    except Exception:
        pass
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    conn = get_db_connection()
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
    else:
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
        conn.close()
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
@st.cache_data(ttl=3600)
def get_all_teachers_from_db_cached():
    conn = get_db_connection()
    if hasattr(conn, 'session'):
        df = conn.query('SELECT * FROM teachers', ttl=0)
        return df.to_dict(orient='records')
    else:
        cursor = conn.cursor()
        teachers = cursor.execute('SELECT * FROM teachers').fetchall()
        conn.close()
        return [dict(t) for t in teachers]

def get_teacher_by_id_from_db(teacher_id):
    conn = get_db_connection()
    if hasattr(conn, 'session'):
        try:
            teacher = conn.query(f'SELECT * FROM teachers WHERE id = {teacher_id}', ttl=0).iloc[0].to_dict()
            return teacher
        except IndexError:
            return None
    else:
        cursor = conn.cursor()
        teacher = cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,)).fetchone()
        conn.close()
        return dict(teacher) if teacher else None

def add_teacher_to_db(full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None):
    conn = get_db_connection()
    saved_photo_path = None
    if photo_file:
        try:
            extension = os.path.splitext(photo_file.name)[1]
            new_filename = f"{os.path.splitext(photo_file.name)[0]}_{os.urandom(8).hex()}{extension}"
            saved_photo_path_full = os.path.join(UPLOAD_FOLDER, new_filename)
            
            with open(saved_photo_path_full, "wb") as f:
                f.write(photo_file.getbuffer())
            saved_photo_path = new_filename
            st.toast(f"บันทึกรูปภาพ: {saved_photo_path_full}", icon="📸")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพ: {e}")
            saved_photo_path = None

    if hasattr(conn, 'session'):
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
    else:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO teachers (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_path)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, saved_photo_path))
        conn.commit()
        conn.close()
    st.cache_data.clear()
    st.success(f"เพิ่มข้อมูลครู '{full_name}' สำเร็จ!")

def update_teacher_in_db(teacher_id, full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None):
    conn = get_db_connection()
    current_teacher = get_teacher_by_id_from_db(teacher_id)

    if not current_teacher:
        st.error("ไม่พบครูที่ต้องการแก้ไข")
        return False

    updates = []
    params = {}

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
    
    if photo_file:
        if current_teacher and current_teacher['photo_path']:
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
            saved_photo_path = new_filename
            updates.append("photo_path = :photo_path")
            params['photo_path'] = saved_photo_path
            st.toast(f"บันทึกรูปภาพใหม่: {saved_photo_path_full}", icon="📸")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพใหม่: {e}")
            
    elif st.session_state.get('photo_cleared', False):
        if current_teacher and current_teacher['photo_path']:
            old_photo_full_path = os.path.join(UPLOAD_FOLDER, current_teacher['photo_path'])
            if os.path.exists(old_photo_full_path):
                try:
                    os.remove(old_photo_full_path)
                    st.info(f"ลบรูปภาพ (ตามคำสั่ง): {old_photo_full_path}")
                except Exception as e:
                    st.warning(f"เกิดข้อผิดพลาดในการลบรูปภาพ (ตามคำสั่ง): {e}")
        updates.append("photo_path = :photo_path")
        params['photo_path'] = None

    if not updates:
        st.info("ไม่มีข้อมูลที่เปลี่ยนแปลง")
        return False

    params['id'] = teacher_id
    query = f"UPDATE teachers SET {', '.join(updates)} WHERE id = :id"
    
    if hasattr(conn, 'session'):
        with conn.session as s:
            s.execute(query, params=params)
            s.commit()
    else:
        cursor = conn.cursor()
        st.error("การอัปเดตข้อมูลผ่าน SQLite โดยตรงไม่รองรับการอัปเดตแบบไดนามิกหลายฟิลด์อย่างสมบูรณ์ด้วยวิธีการนี้")
        conn.close()
        return False
    st.cache_data.clear()
    st.success(f"ข้อมูลครู ID {teacher_id} อัปเดตสำเร็จ!")
    return True

def delete_teacher_from_db(teacher_id):
    conn = get_db_connection()
    teacher_to_delete = get_teacher_by_id_from_db(teacher_id)

    if not teacher_to_delete:
        st.error(f"ไม่พบครู ID {teacher_id} ที่ต้องการลบ")
        return False

    if hasattr(conn, 'session'):
        with conn.session as s:
            s.execute('DELETE FROM teachers WHERE id = :id', params=dict(id=teacher_id))
            s.commit()
    else:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM teachers WHERE id = ?', (teacher_id,))
        conn.commit()
        conn.close()

    if teacher_to_delete and teacher_to_delete['photo_path']:
        photo_full_path = os.path.join(UPLOAD_FOLDER, teacher_to_delete['photo_path'])
        if os.path.exists(photo_full_path):
            try:
                os.remove(photo_full_path)
                st.info(f"ลบรูปภาพ: {photo_full_path}")
            except Exception as e:
                st.warning(f"เกิดข้อผิดพลาดในการลบไฟล์รูปภาพ: {e}")
    st.cache_data.clear()
    st.success(f"ข้อมูลครู ID {teacher_id} ถูกลบสำเร็จ!")
    return True

# --- Streamlit App UI ---

# กำหนดการตั้งค่าหน้าเว็บ
st.set_page_config(
    layout="wide", 
    page_title="ระบบจัดการฐานข้อมูลครูกลุ่มโรงเรียนบ้านด่าน 2",
    page_icon="🏫"  
)

# --- ส่วนหัว: ชื่อระบบและโลโก้ ---
# สร้างคอลัมน์เพื่อจัดวางชื่อและโลโก้
# กำหนดสัดส่วนของคอลัมน์เพื่อให้ชื่อมีพื้นที่มากพอ และโลโก้มีพื้นที่น้อยลง (เช่น 5:1)
col_text, col_logo = st.columns([5, 1])

with col_text:
    # ใช้ st.markdown เพื่อให้สามารถแสดงข้อความหัวข้อและควบคุมการจัดวางได้ยืดหยุ่นกว่า st.title
    st.markdown("## 👨‍🏫 ระบบจัดการฐานข้อมูลครูกลุ่มโรงเรียนบ้านด่าน 2", unsafe_allow_html=True)

with col_logo:
    logo_path = "ban_dan_2_logo.png"  # **ตรวจสอบให้แน่ใจว่า path นี้ถูกต้อง**
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path)
            # st.image จะวางรูปภาพในแนวตั้งตรงกลางคอลัมน์
            # ใช้ width=100 หรือตามความเหมาะสม เพื่อให้โลโก้มีขนาดเล็กพอที่จะอยู่ข้างชื่อ
            st.image(logo, width=100) 
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการโหลดโลโก้: {e}")
    else:
        st.warning(f"ไม่พบไฟล์โลโก้ที่: {logo_path}")

st.markdown("---") # เส้นคั่นแนวนอน

# กำหนดสถานะเริ่มต้นของ Session
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'list'
if 'edit_teacher_id' not in st.session_state:
    st.session_state.edit_teacher_id = None
if 'photo_cleared' not in st.session_state:
    st.session_state.photo_cleared = False

setup_database()

# --- Navigation Buttons ---
col1, col2, _ = st.columns([1,1,4]) 
with col1:
    if st.button("แสดงข้อมูลครูทั้งหมด", key="show_all", use_container_width=True):
        st.session_state.current_view = 'list'
        st.session_state.edit_teacher_id = None
        st.session_state.photo_cleared = False
        st.rerun()
with col2:
    if st.button("เพิ่มข้อมูลครูใหม่", key="add_new", use_container_width=True):
        st.session_state.current_view = 'add'
        st.session_state.edit_teacher_id = None
        st.session_state.photo_cleared = False
        st.rerun()

st.markdown("---") 

# --- Content Area ---
if st.session_state.current_view == 'list':
    st.header("รายการข้อมูลครู")
    teachers = get_all_teachers_from_db_cached()

    if teachers:
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
                    if os.path.exists(photo_full_path):
                        st.image(photo_path_full, caption=f"รูป {teacher['full_name']}", width=150)
                    else:
                        st.warning("ไม่พบไฟล์รูปภาพ")
                else:
                    st.info("ไม่มีรูปภาพ")
                
                edit_button = st.button(f"แก้ไข ID {teacher['id']}", key=f"edit_teacher_{teacher['id']}", use_container_width=True)
                delete_button = st.button(f"ลบ ID {teacher['id']}", key=f"delete_teacher_{teacher['id']}", use_container_width=True)
                
                if edit_button:
                    st.session_state.current_view = 'edit'
                    st.session_state.edit_teacher_id = teacher['id']
                    st.rerun()
                
                if delete_button:
                    if st.session_state.get(f'confirm_delete_{teacher["id"]}', False):
                        if delete_teacher_from_db(teacher['id']):
                            st.session_state.current_view = 'list'
                        del st.session_state[f'confirm_delete_{teacher["id"]}']
                        st.rerun()
                    else:
                        st.session_state[f'confirm_delete_{teacher["id"]}'] = True
                        st.warning(f"คลิก 'ลบ ID {teacher['id']}' อีกครั้งเพื่อยืนยันการลบ '{teacher['full_name']}'")

            st.markdown("---")

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
                st.session_state.current_view = 'list'
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
                new_full_name = st.text_input("ชื่อ-สกุล:", value=teacher_data['full_name'], key="edit_full_name")
                new_school_affiliation = st.text_input("สังกัดโรงเรียน:", value=teacher_data['school_affiliation'] or "", key="edit_school_affiliation")
                new_major_subject = st.text_input("วิชาเอก:", value=teacher_data['major_subject'] or "", key="edit_major_subject")
                new_teaching_subjects = st.text_input("สอนรายวิชา (คั่นด้วยคอมม่า):", value=teacher_data['teaching_subjects'] or "", key="edit_teaching_subjects")
                new_contact_number = st.text_input("เบอร์ติดต่อ:", value=teacher_data['contact_number'] or "", key="edit_contact_number")

                if teacher_data['photo_path']:
                    photo_path_full = os.path.join(UPLOAD_FOLDER, teacher_data['photo_path'])
                    if os.path.exists(photo_full_path):
                        st.image(photo_full_path, caption="รูปภาพปัจจุบัน", width=150)
                    else:
                        st.warning("ไม่พบไฟล์รูปภาพปัจจุบันในโฟลเดอร์")
                else:
                    st.info("ยังไม่มีรูปภาพสำหรับครูคนนี้")

                new_photo_file = st.file_uploader("เปลี่ยนรูปถ่ายใบหน้า (เลือกไฟล์ใหม่):", type=["png", "jpg", "jpeg"], key="edit_photo_uploader")
                
                clear_photo = st.checkbox("ลบรูปภาพปัจจุบัน", value=st.session_state.get('photo_cleared', False), key="clear_current_photo")
                st.session_state.photo_cleared = clear_photo

                submitted = st.form_submit_button("บันทึกการแก้ไข")
                if submitted:
                    if not new_full_name:
                        st.error("ชื่อ-สกุล ต้องไม่ว่างเปล่า!")
                    else:
                        photo_to_save = new_photo_file
                        if st.session_state.photo_cleared:
                            photo_to_save = None

                        if update_teacher_in_db(
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
                            st.session_state.photo_cleared = False
                            st.rerun()
        else:
            st.error("ไม่พบข้อมูลครูที่ต้องการแก้ไข")
            st.session_state.current_view = 'list'
            st.rerun()
