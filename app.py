import streamlit as st
import sqlite3
import os
import shutil
from PIL import Image
import pandas as pd

# --- Configuration ---
DATABASE_NAME = 'teacher_management.db'
PHOTO_DIR = 'teacher_photos'
UPLOAD_FOLDER = PHOTO_DIR 

# --- Database Setup and Functions ---

def get_db_connection():
    """
    สร้างและส่งคืนการเชื่อมต่อฐานข้อมูล SQLite.
    พยายามใช้ st.connection ถ้ามี, ไม่เช่นนั้นจะ fallback ไปใช้ sqlite3 โดยตรง.
    """
    try:
        if "connections" in st.secrets and "teacher_db" in st.secrets["connections"]:
            # ใช้ st.connection สำหรับการ deploy บน Streamlit Community Cloud
            return st.connection('teacher_db', type='sql')
    except Exception:
        pass # หากไม่มี st.secrets หรือเกิดข้อผิดพลาด ให้ลองใช้ sqlite3 โดยตรง
    
    # Fallback สำหรับการรันแบบ local หรือกรณีไม่มี st.connection
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row # ทำให้สามารถเข้าถึงคอลัมน์ด้วยชื่อได้
    return conn

def setup_database():
    """
    ตั้งค่าตาราง 'teachers' ในฐานข้อมูลหากยังไม่มี
    และสร้างโฟลเดอร์สำหรับเก็บรูปภาพ
    รวมถึงเพิ่มคอลัมน์ 'position' หากยังไม่มี (เพื่อรองรับการอัปเดตโครงสร้าง)
    """
    conn = get_db_connection()
    
    if hasattr(conn, 'session'):
        # สำหรับ st.connection (เช่นบน Streamlit Community Cloud)
        with conn.session as s:
            s.execute('''
                CREATE TABLE IF NOT EXISTS teachers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    school_affiliation TEXT,
                    major_subject TEXT,
                    teaching_subjects TEXT,
                    contact_number TEXT,
                    photo_path TEXT,
                    position TEXT  
                )
            ''')
            s.commit()
            
            # ตรวจสอบและเพิ่มคอลัมน์ 'position' หากยังไม่มี (เพื่อรองรับฐานข้อมูลเก่า)
            cursor = s.connection.cursor() # เข้าถึง sqlite3 cursor จาก st.connection
            cursor.execute("PRAGMA table_info(teachers)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'position' not in columns:
                s.execute("ALTER TABLE teachers ADD COLUMN position TEXT")
                s.commit()
    else:
        # สำหรับ sqlite3 โดยตรง (เช่นการรันแบบ local)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                school_affiliation TEXT,
                major_subject TEXT,
                teaching_subjects TEXT,
                contact_number TEXT,
                photo_path TEXT,
                position TEXT  
            )
        ''')
        conn.commit()
        
        # ตรวจสอบและเพิ่มคอลัมน์ 'position' หากยังไม่มี
        cursor.execute("PRAGMA table_info(teachers)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'position' not in columns:
            cursor.execute("ALTER TABLE teachers ADD COLUMN position TEXT")
            conn.commit()
        conn.close() # ปิดการเชื่อมต่อเมื่อเสร็จสิ้นการตั้งค่า

    # สร้างโฟลเดอร์สำหรับเก็บรูปภาพ หากยังไม่มี
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

@st.cache_data(ttl=3600)
def get_all_teachers_from_db_cached():
    """
    ดึงข้อมูลครูทั้งหมดจากฐานข้อมูลและเก็บไว้ใน cache เพื่อประสิทธิภาพ.
    """
    conn = get_db_connection()
    if hasattr(conn, 'session'):
        # สำหรับ st.connection
        df = conn.query('SELECT * FROM teachers', ttl=0) 
        return df.to_dict(orient='records')
    else:
        # สำหรับ sqlite3 โดยตรง
        cursor = conn.cursor()
        teachers = cursor.execute('SELECT * FROM teachers').fetchall()
        conn.close()
        return [dict(t) for t in teachers]

def export_teachers_to_excel():
    """
    ส่งออกข้อมูลครูทั้งหมดเป็นไฟล์ Excel (.xlsx).
    """
    conn = get_db_connection()
    if hasattr(conn, 'session'):
        # สำหรับ st.connection
        df = conn.query('SELECT * FROM teachers', ttl=0)
    else:
        # สำหรับ sqlite3 โดยตรง
        cursor = conn.cursor()
        # เลือกคอลัมน์ทั้งหมด รวมถึง 'position'
        cursor.execute("SELECT id, full_name, school_affiliation, position, major_subject, teaching_subjects, contact_number, photo_path FROM teachers")
        data = cursor.fetchall()
        column_names = [description[0] for description in cursor.description]
        conn.close()
        df = pd.DataFrame(data, columns=column_names)

    # เปลี่ยนชื่อคอลัมน์ให้เป็นภาษาไทยที่เข้าใจง่าย
    df.rename(columns={
        'id': 'รหัสครู',
        'full_name': 'ชื่อ-สกุล',
        'school_affiliation': 'สังกัดโรงเรียน',
        'position': 'ตำแหน่ง', 
        'major_subject': 'วิชาเอก',
        'teaching_subjects': 'สอนรายวิชา',
        'contact_number': 'เบอร์ติดต่อ',
        'photo_path': 'เส้นทางไฟล์รูปภาพ'
    }, inplace=True)
    
    # บันทึกเป็นไฟล์ Excel
    output = pd.ExcelWriter('teachers_data.xlsx', engine='xlsxwriter')
    df.to_excel(output, index=False, sheet_name='ข้อมูลครู')
    output.close() 

    # อ่านไฟล์ Excel และส่งกลับข้อมูล
    with open('teachers_data.xlsx', 'rb') as f:
        file_data = f.read()
    os.remove('teachers_data.xlsx') # ลบไฟล์ชั่วคราว
    return file_data

def get_teacher_by_id_from_db(teacher_id):
    """
    ดึงข้อมูลครูตาม ID ที่ระบุ.
    """
    conn = get_db_connection()
    if hasattr(conn, 'session'):
        # สำหรับ st.connection
        try:
            teacher = conn.query(f'SELECT * FROM teachers WHERE id = {teacher_id}', ttl=0).iloc[0].to_dict()
            return teacher
        except IndexError:
            return None # ไม่พบข้อมูล
    else:
        # สำหรับ sqlite3 โดยตรง
        cursor = conn.cursor()
        teacher = cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,)).fetchone()
        conn.close()
        return dict(teacher) if teacher else None

def add_teacher_to_db(full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None, position=None):
    """
    เพิ่มข้อมูลครูใหม่ลงในฐานข้อมูล.
    """
    conn = get_db_connection()
    saved_photo_path = None
    if photo_file:
        try:
            # บันทึกรูปภาพลงในโฟลเดอร์ UPLOAD_FOLDER ด้วยชื่อไฟล์ที่ไม่ซ้ำกัน
            extension = os.path.splitext(photo_file.name)[1]
            new_filename = f"{os.path.splitext(photo_file.name)[0]}_{os.urandom(8).hex()}{extension}"
            saved_photo_path_full = os.path.join(UPLOAD_FOLDER, new_filename)
            
            with open(saved_photo_path_full, "wb") as f:
                f.write(photo_file.getbuffer())
            saved_photo_path = new_filename # เก็บเฉพาะชื่อไฟล์สำหรับฐานข้อมูล
            st.toast(f"บันทึกรูปภาพ: {saved_photo_path_full}", icon="📸")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพ: {e}")
            saved_photo_path = None

    if hasattr(conn, 'session'):
        # สำหรับ st.connection
        with conn.session as s:
            s.execute('''
                INSERT INTO teachers (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_path, position)
                VALUES (:full_name, :school_affiliation, :major_subject, :teaching_subjects, :contact_number, :photo_path, :position)
            ''', params=dict(
                full_name=full_name,
                school_affiliation=school_affiliation,
                major_subject=major_subject,
                teaching_subjects=teaching_subjects,
                contact_number=contact_number,
                photo_path=saved_photo_path,
                position=position
            ))
            s.commit()
    else:
        # สำหรับ sqlite3 โดยตรง
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO teachers (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_path, position)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, saved_photo_path, position))
        conn.commit()
        conn.close()
    st.cache_data.clear() # ล้าง cache เพื่อให้ข้อมูลล่าสุดถูกดึงมาแสดง
    st.success(f"เพิ่มข้อมูลครู '{full_name}' สำเร็จ!")

def update_teacher_in_db(teacher_id, full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None, position=None):
    """
    แก้ไขข้อมูลครูในฐานข้อมูลตาม ID ที่ระบุ.
    """
    conn = get_db_connection()
    current_teacher = get_teacher_by_id_from_db(teacher_id)

    if not current_teacher:
        st.error("ไม่พบครูที่ต้องการแก้ไข")
        return False

    updates = []
    # ใช้ List สำหรับเก็บค่าพารามิเตอร์แบบ Positional สำหรับ sqlite3 โดยตรง
    params = [] 

    # ตรวจสอบว่ามีการเปลี่ยนแปลงข้อมูลในแต่ละฟิลด์หรือไม่
    if full_name is not None and full_name != current_teacher['full_name']:
        updates.append("full_name = ?")
        params.append(full_name)
    if school_affiliation is not None and school_affiliation != current_teacher['school_affiliation']:
        updates.append("school_affiliation = ?")
        params.append(school_affiliation)
    if major_subject is not None and major_subject != current_teacher['major_subject']:
        updates.append("major_subject = ?")
        params.append(major_subject)
    if teaching_subjects is not None and teaching_subjects != current_teacher['teaching_subjects']:
        updates.append("teaching_subjects = ?")
        params.append(teaching_subjects)
    if contact_number is not None and contact_number != current_teacher['contact_number']:
        updates.append("contact_number = ?")
        params.append(contact_number)
    # เพิ่มการอัปเดตตำแหน่ง
    if position is not None and position != current_teacher.get('position', ''): 
        updates.append("position = ?")
        params.append(position)
    
    saved_photo_path = None # กำหนดค่าเริ่มต้นสำหรับ saved_photo_path
    if photo_file:
        # ถ้ามีไฟล์รูปภาพใหม่ถูกอัปโหลด
        if current_teacher and current_teacher['photo_path']:
            # ลบรูปภาพเก่าออกก่อน
            old_photo_full_path = os.path.join(UPLOAD_FOLDER, current_teacher['photo_path'])
            if os.path.exists(old_photo_full_path):
                try:
                    os.remove(old_photo_full_path)
                    st.info(f"ลบรูปภาพเก่า: {old_photo_full_path}")
                except Exception as e:
                    st.warning(f"เกิดข้อผิดพลาดในการลบรูปภาพเก่า: {e}")
        try:
            # บันทึกรูปภาพใหม่
            extension = os.path.splitext(photo_file.name)[1]
            new_filename = f"{os.path.splitext(photo_file.name)[0]}_{os.urandom(8).hex()}{extension}"
            saved_photo_path_full = os.path.join(UPLOAD_FOLDER, new_filename)
            with open(saved_photo_path_full, "wb") as f:
                f.write(photo_file.getbuffer())
            saved_photo_path = new_filename
            updates.append("photo_path = ?")
            params.append(saved_photo_path)
            st.toast(f"บันทึกรูปภาพใหม่: {saved_photo_path_full}", icon="📸")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพใหม่: {e}")
            
    elif st.session_state.get('photo_cleared', False):
        # ถ้า checkbox 'ลบรูปภาพปัจจุบัน' ถูกเลือก
        if current_teacher and current_teacher['photo_path']:
            old_photo_full_path = os.path.join(UPLOAD_FOLDER, current_teacher['photo_path'])
            if os.path.exists(old_photo_full_path):
                try:
                    os.remove(old_photo_full_path)
                    st.info(f"ลบรูปภาพ (ตามคำสั่ง): {old_photo_full_path}")
                except Exception as e:
                    st.warning(f"เกิดข้อผิดพลาดในการลบรูปภาพ (ตามคำสั่ง): {e}")
        updates.append("photo_path = ?")
        params.append(None) # ตั้งค่า photo_path เป็น NULL ในฐานข้อมูล

    if not updates:
        st.info("ไม่มีข้อมูลที่เปลี่ยนแปลง")
        return False

    params.append(teacher_id) # เพิ่ม ID ของครูเป็นพารามิเตอร์สุดท้ายสำหรับ WHERE clause
    # สร้างคำสั่ง SQL สำหรับ UPDATE โดยใช้ Positional Parameters (?)
    query = f"UPDATE teachers SET {', '.join(updates)} WHERE id = ?"
    
    if hasattr(conn, 'session'):
        # สำหรับ st.connection (ใช้ Named Parameters)
        named_params = {}
        # คัดลอกค่าจาก params list ไปยัง named_params dictionary
        # ตรวจสอบและเพิ่มเฉพาะคอลัมน์ที่มีการเปลี่ยนแปลง
        if full_name is not None and full_name != current_teacher['full_name']:
            named_params['full_name'] = full_name
        if school_affiliation is not None and school_affiliation != current_teacher['school_affiliation']:
            named_params['school_affiliation'] = school_affiliation
        if major_subject is not None and major_subject != current_teacher['major_subject']:
            named_params['major_subject'] = major_subject
        if teaching_subjects is not None and teaching_subjects != current_teacher['teaching_subjects']:
            named_params['teaching_subjects'] = teaching_subjects
        if contact_number is not None and contact_number != current_teacher['contact_number']:
            named_params['contact_number'] = contact_number
        if position is not None and position != current_teacher.get('position', ''):
            named_params['position'] = position

        # จัดการ photo_path สำหรับ named_params
        if photo_file:
            # ต้องสร้าง saved_photo_path อีกครั้งเพื่อให้ named_params มีค่าที่ถูกต้อง
            try:
                extension = os.path.splitext(photo_file.name)[1]
                new_filename = f"{os.path.splitext(photo_file.name)[0]}_{os.urandom(8).hex()}{extension}"
                saved_photo_path_full = os.path.join(UPLOAD_FOLDER, new_filename)
                with open(saved_photo_path_full, "wb") as f:
                    f.write(photo_file.getbuffer())
                saved_photo_path = new_filename
                named_params['photo_path'] = saved_photo_path
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพใหม่: {e}")
                named_params['photo_path'] = None 
        elif st.session_state.get('photo_cleared', False):
            named_params['photo_path'] = None

        named_params['id'] = teacher_id
        
        # สร้าง query string ที่มี named parameters สำหรับ st.connection
        # เฉพาะคอลัมน์ที่อยู่ใน named_params (ยกเว้น 'id')
        named_updates_clause = []
        for key in named_params.keys():
            if key != 'id': 
                named_updates_clause.append(f"{key} = :{key}")
        named_query = f"UPDATE teachers SET {', '.join(named_updates_clause)} WHERE id = :id"

        with conn.session as s:
            s.execute(named_query, params=named_params)
            s.commit()
    else:
        # สำหรับ sqlite3 โดยตรง (ใช้ Positional Parameters)
        cursor = conn.cursor()
        cursor.execute(query, tuple(params)) # ส่ง List ของพารามิเตอร์เป็น Tuple
        conn.commit()
        conn.close()
    st.cache_data.clear()
    st.success(f"ข้อมูลครู ID {teacher_id} อัปเดตสำเร็จ!")
    return True

def delete_teacher_from_db(teacher_id):
    """
    ลบข้อมูลครูและรูปภาพที่เกี่ยวข้องออกจากฐานข้อมูลและโฟลเดอร์.
    """
    conn = get_db_connection()
    teacher_to_delete = get_teacher_by_id_from_db(teacher_id)

    if not teacher_to_delete:
        st.error(f"ไม่พบครู ID {teacher_id} ที่ต้องการลบ")
        return False

    if hasattr(conn, 'session'):
        # สำหรับ st.connection
        with conn.session as s:
            s.execute('DELETE FROM teachers WHERE id = :id', params=dict(id=teacher_id))
            s.commit()
    else:
        # สำหรับ sqlite3 โดยตรง
        cursor = conn.cursor()
        cursor.execute('DELETE FROM teachers WHERE id = ?', (teacher_id,))
        conn.commit()
        conn.close()

    # ลบไฟล์รูปภาพที่เกี่ยวข้อง
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

# เพิ่ม CSS สำหรับสไตล์ Minimal
st.markdown("""
<style>
    /* ซ่อนเมนูเบอร์เกอร์และปุ่ม Deploy */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* ปรับขนาดฟอนต์ของหัวข้อหลัก */
    h1, h2, h3, h4, h5, h6 {
        color: #333; /* สีเข้มขึ้น */
        font-family: 'Sarabun', sans-serif; /* ลองใช้ฟอนต์ที่สะอาดตา */
    }
    
    /* ปรับปุ่มให้ดู Minimal ขึ้น */
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #e0e0e0;
        background-color: #f5f5f5;
        color: #333;
        padding: 8px 15px;
        font-size: 14px;
        transition: all 0.2s ease-in-out;
    }
    .stButton > button:hover {
        background-color: #e0e0e0;
        border-color: #ccc;
    }

    /* ปุ่มหลัก (primary button) */
    .stButton > button.primary {
        background-color: #4CAF50; /* เขียว */
        color: white;
        border: none;
    }
    .stButton > button.primary:hover {
        background-color: #45a049; /* เขียวเข้มขึ้นเมื่อ hover */
    }

    /* สไตล์สำหรับ input fields */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 1px solid #ccc;
        padding: 8px 12px;
    }

    /* สไตล์สำหรับ expander */
    .streamlit-expanderHeader {
        background-color: #f0f2f6; /* สีพื้นหลังของ header */
        border-radius: 8px;
        padding: 10px;
        font-weight: bold;
    }
    .streamlit-expanderContent {
        border: 1px solid #e0e0e0;
        border-top: none;
        border-bottom-left-radius: 8px;
        border-bottom-right-radius: 8px;
        padding: 15px;
        background-color: #ffffff;
    }
</style>
""", unsafe_allow_html=True)


# กำหนดสถานะเริ่มต้นของ Session
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'list'
if 'edit_teacher_id' not in st.session_state:
    st.session_state.edit_teacher_id = None
if 'photo_cleared' not in st.session_state:
    st.session_state.photo_cleared = False
if 'search_query_school' not in st.session_state:
    st.session_state.search_query_school = ""

# ตั้งค่าฐานข้อมูล (สร้างตาราง/โฟลเดอร์ หากยังไม่มี)
setup_database()

# --- ส่วนหัว: ชื่อระบบและโลโก้ ---
header_container = st.container()
with header_container:
    col_text, col_logo = st.columns([5, 1])
    with col_text:
        st.markdown("## 👨‍🏫 **ระบบจัดการฐานข้อมูลครูกลุ่มโรงเรียนบ้านด่าน 2**", unsafe_allow_html=True)
    with col_logo:
        logo_path = "ban_dan_2_logo.png"  # ตรวจสอบให้แน่ใจว่าไฟล์โลโก้อยู่ในที่ถูกต้อง
        if os.path.exists(logo_path):
            try:
                logo = Image.open(logo_path)
                st.image(logo, width=100)  # ปรับขนาดตามต้องการ
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการโหลดโลโก้: {e}")
        else:
            st.warning(f"ไม่พบไฟล์โลโก้ที่: {logo_path}")

st.markdown("---")  # เส้นแบ่ง

# --- Navigation Buttons and Export ---
nav_container = st.container()
with nav_container:
    # แบ่งคอลัมน์สำหรับปุ่มนำทางและการส่งออก
    col1, col2, col3, _ = st.columns([1,1,1,3])  
    with col1:
        if st.button("📚 แสดงข้อมูลครูทั้งหมด", key="show_all", use_container_width=True):
            st.session_state.current_view = 'list'
            st.session_state.edit_teacher_id = None
            st.session_state.photo_cleared = False
            st.session_state.search_query_school = "" # ล้างการค้นหาเมื่อกลับไปหน้ารายการ
            st.rerun() # รีรันเพื่ออัปเดต UI
    with col2:
        if st.button("➕ เพิ่มข้อมูลครูใหม่", key="add_new", use_container_width=True):
            st.session_state.current_view = 'add'
            st.session_state.edit_teacher_id = None
            st.session_state.photo_cleared = False
            st.rerun()
    with col3:
        # ปุ่มดาวน์โหลดไฟล์ Excel
        excel_file_data = export_teachers_to_excel()
        st.download_button(
            label="⬇️ Export ข้อมูลครู (.xlsx)",  
            data=excel_file_data,
            file_name="ข้อมูลครู_กลุ่มโรงเรียนบ้านด่าน2.xlsx",  
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  
            key="download_excel_button",
            use_container_width=True
        )

st.markdown("---")  # เส้นแบ่ง

# --- Content Area ---
content_container = st.container()
with content_container:
    if st.session_state.current_view == 'list':
        st.header("รายการข้อมูลครู")

        # --- ส่วนค้นหา ---
        with st.expander("🔎 ค้นหาข้อมูลครู", expanded=False):
            search_col_input, search_col_button = st.columns([3, 1])
            with search_col_input:
                search_term = st.text_input(
                    "ค้นหาสังกัดโรงเรียน:",  
                    value=st.session_state.search_query_school,  
                    key="school_search_input",
                    placeholder="เช่น บ้านด่านเหนือ"
                )
            with search_col_button:
                st.write("") # เว้นวรรคเพื่อให้ปุ่มอยู่ต่ำลงเล็กน้อย
                if st.button("ค้นหา", key="search_button", use_container_width=True):
                    st.session_state.search_query_school = search_term
        
        st.markdown("<br>", unsafe_allow_html=True)  # เพิ่มช่องว่าง

        teachers = get_all_teachers_from_db_cached()
        
        # กรองข้อมูลตามคำค้นหา
        if st.session_state.search_query_school:
            search_lower = st.session_state.search_query_school.lower()
            filtered_teachers = [
                t for t in teachers  
                if t['school_affiliation'] and search_lower in t['school_affiliation'].lower()
            ]
            st.info(f"แสดงผลการค้นหาสำหรับสังกัดโรงเรียน: '{st.session_state.search_query_school}' ({len(filtered_teachers)} รายการ)")
            teachers_to_display = filtered_teachers
        else:
            teachers_to_display = teachers

        if teachers_to_display:
            # วนลูปแสดงข้อมูลครูแต่ละคนในรูปแบบ Card
            for teacher in teachers_to_display:  
                teacher_card = st.container(border=True)  # สร้าง Card พร้อมเส้นขอบ
                with teacher_card:
                    col_left, col_right = st.columns([2, 1]) # แบ่ง 2 คอลัมน์ภายใน Card
                    with col_left:
                        st.markdown(f"### {teacher['full_name']} (ID: {teacher['id']})")
                        st.markdown(f"**ตำแหน่ง:** {teacher.get('position', '-') or '-'}") # แสดงตำแหน่ง (ใช้ .get เพื่อป้องกัน KeyError ในข้อมูลเก่าที่อาจไม่มีคอลัมน์นี้)
                        st.markdown(f"**สังกัดโรงเรียน:** {teacher['school_affiliation'] or '-'}")
                        st.markdown(f"**วิชาเอก:** {teacher['major_subject'] or '-'}")
                        st.markdown(f"**สอนรายวิชา:** {teacher['teaching_subjects'] or '-'}")
                        st.markdown(f"**เบอร์ติดต่อ:** {teacher['contact_number'] or '-'}")
                    with col_right:
                        if teacher['photo_path']:
                            photo_path_full = os.path.join(UPLOAD_FOLDER, teacher['photo_path'])
                            if os.path.exists(photo_path_full):
                                st.image(photo_path_full, caption=f"รูป {teacher['full_name']}", width=150)
                            else:
                                st.warning("ไม่พบไฟล์รูปภาพ")
                        else:
                            st.info("ไม่มีรูปภาพ")
                    
                        st.markdown("<br>", unsafe_allow_html=True)  # เพิ่มช่องว่างก่อนปุ่ม
                        # ปุ่มแก้ไขและลบ
                        edit_button = st.button(f"✏️ แก้ไข", key=f"edit_teacher_{teacher['id']}", use_container_width=True)
                        delete_button = st.button(f"🗑️ ลบ", key=f"delete_teacher_{teacher['id']}", use_container_width=True)
                        
                        if edit_button:
                            st.session_state.current_view = 'edit'
                            st.session_state.edit_teacher_id = teacher['id']
                            st.rerun() # รีรันเพื่อไปหน้าแก้ไข
                        
                        if delete_button:
                            # กลไกยืนยันการลบสองชั้น
                            if st.session_state.get(f'confirm_delete_{teacher["id"]}', False):
                                # ปุ่มยืนยันการลบจริง
                                if st.button("ยืนยันการลบ", key=f"confirm_delete_final_{teacher['id']}", type="primary", use_container_width=True):
                                    if delete_teacher_from_db(teacher['id']):
                                        st.session_state.current_view = 'list'
                                    del st.session_state[f'confirm_delete_{teacher["id"]}'] # ลบสถานะยืนยัน
                                    st.rerun()
                            else:
                                # แสดงข้อความเตือนให้ยืนยันการลบ
                                st.session_state[f'confirm_delete_{teacher["id"]}'] = True
                                st.warning(f"คลิก 'ยืนยันการลบ' เพื่อลบ '{teacher['full_name']}'")
                st.markdown("<br>", unsafe_allow_html=True)  # เพิ่มช่องว่างระหว่าง Card

        else:
            st.info("ไม่พบข้อมูลครูในระบบ หรือไม่พบผลการค้นหา")

    elif st.session_state.current_view == 'add':
        st.header("เพิ่มข้อมูลครูใหม่")
        with st.form("add_teacher_form", clear_on_submit=True):
            full_name = st.text_input("ชื่อ-สกุล:", key="add_full_name")
            position = st.text_input("ตำแหน่ง:", key="add_position", placeholder="เช่น ครูผู้ช่วย, ครูชำนาญการ")
            school_affiliation = st.text_input("สังกัดโรงเรียน:", key="add_school_affiliation")
            major_subject = st.text_input("วิชาเอก:", key="add_major_subject")
            teaching_subjects = st.text_input("สอนรายวิชา (คั่นด้วยคอมม่า):", key="add_teaching_subjects")
            contact_number = st.text_input("เบอร์ติดต่อ:", key="add_contact_number")
            photo_file = st.file_uploader("รูปถ่ายใบหน้า:", type=["png", "jpg", "jpeg"], key="add_photo_uploader")

            submitted = st.form_submit_button("💾 บันทึกข้อมูลครู", type="primary")
            if submitted:
                if full_name:
                    add_teacher_to_db(full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file, position)
                    st.session_state.current_view = 'list' # กลับไปหน้ารายการหลังจากบันทึก
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
                    # แสดงข้อมูลปัจจุบันในช่องกรอก
                    new_full_name = st.text_input("ชื่อ-สกุล:", value=teacher_data['full_name'] or "", key="edit_full_name")
                    new_position = st.text_input("ตำแหน่ง:", value=teacher_data.get('position', '') or "", key="edit_position")
                    new_school_affiliation = st.text_input("สังกัดโรงเรียน:", value=teacher_data['school_affiliation'] or "", key="edit_school_affiliation")
                    new_major_subject = st.text_input("วิชาเอก:", value=teacher_data['major_subject'] or "", key="edit_major_subject")
                    new_teaching_subjects = st.text_input("สอนรายวิชา (คั่นด้วยคอมม่า):", value=teacher_data['teaching_subjects'] or "", key="edit_teaching_subjects")
                    new_contact_number = st.text_input("เบอร์ติดต่อ:", value=teacher_data['contact_number'] or "", key="edit_contact_number")

                    # แสดงรูปภาพปัจจุบัน (ถ้ามี)
                    if teacher_data['photo_path']:
                        photo_path_full = os.path.join(UPLOAD_FOLDER, teacher_data['photo_path'])
                        if os.path.exists(photo_path_full):
                            st.image(photo_path_full, caption="รูปภาพปัจจุบัน", width=150)
                        else:
                            st.warning("ไม่พบไฟล์รูปภาพปัจจุบันในโฟลเดอร์")
                    else:
                        st.info("ยังไม่มีรูปภาพสำหรับครูคนนี้")

                    # อัปโหลดรูปภาพใหม่
                    new_photo_file = st.file_uploader("เปลี่ยนรูปถ่ายใบหน้า (เลือกไฟล์ใหม่):", type=["png", "jpg", "jpeg"], key="edit_photo_uploader")
                    
                    # Checkbox สำหรับลบรูปภาพปัจจุบัน
                    clear_photo = st.checkbox("ลบรูปภาพปัจจุบัน", value=st.session_state.get('photo_cleared', False), key="clear_current_photo")
                    st.session_state.photo_cleared = clear_photo

                    submitted = st.form_submit_button("📝 บันทึกการแก้ไข", type="primary")
                    if submitted:
                        if not new_full_name:
                            st.error("ชื่อ-สกุล ต้องไม่ว่างเปล่า!")
                        else:
                            photo_to_save = new_photo_file
                            if st.session_state.photo_cleared:
                                photo_to_save = None # ตั้งค่าเป็น None ถ้าเลือกที่จะลบรูปภาพ

                            if update_teacher_in_db(
                                teacher_id_to_edit,
                                new_full_name,
                                new_school_affiliation,
                                new_major_subject,
                                new_teaching_subjects,
                                new_contact_number,
                                photo_to_save,
                                new_position 
                            ):
                                st.session_state.current_view = 'list' # กลับไปหน้ารายการหลังจากแก้ไข
                                st.session_state.edit_teacher_id = None # ล้าง ID ที่กำลังแก้ไข
                                st.session_state.photo_cleared = False # ล้างสถานะการลบรูปภาพ
                                st.rerun()
            else:
                st.error("ไม่พบข้อมูลครูที่ต้องการแก้ไข")
                st.session_state.current_view = 'list'
                st.rerun()
