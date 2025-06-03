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
    try:
        if "connections" in st.secrets and "teacher_db" in st.secrets["connections"]:
            return st.connection('teacher_db', type='sql')
    except Exception:
        pass
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    """
    ตั้งค่าตาราง 'teachers' ในฐานข้อมูลหากยังไม่มี
    และสร้างโฟลเดอร์สำหรับเก็บรูปภาพ
    รวมถึงเพิ่มคอลัมน์ 'position' หากยังไม่มี
    """
    conn = get_db_connection()
    
    if hasattr(conn, 'session'):
        # สำหรับ st.connection
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
                    position TEXT  -- เพิ่มคอลัมน์ position ที่นี่
                )
            ''')
            s.commit()
            
            # ตรวจสอบและเพิ่มคอลัมน์ position หากตารางมีอยู่แล้วแต่ไม่มีคอลัมน์นี้
            # นี่คือวิธีที่ปลอดภัยกว่าการลบและสร้างตารางใหม่
            cursor = s.connection.cursor() # เข้าถึง sqlite3 cursor จาก st.connection
            cursor.execute("PRAGMA table_info(teachers)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'position' not in columns:
                s.execute("ALTER TABLE teachers ADD COLUMN position TEXT")
                s.commit()
    else:
        # สำหรับ sqlite3 โดยตรง
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
                position TEXT  -- เพิ่มคอลัมน์ position ที่นี่
            )
        ''')
        conn.commit()
        
        # ตรวจสอบและเพิ่มคอลัมน์ position หากตารางมีอยู่แล้วแต่ไม่มีคอลัมน์นี้
        cursor.execute("PRAGMA table_info(teachers)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'position' not in columns:
            cursor.execute("ALTER TABLE teachers ADD COLUMN position TEXT")
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

def export_teachers_to_excel():
    conn = get_db_connection()
    if hasattr(conn, 'session'):
        df = conn.query('SELECT * FROM teachers', ttl=0)
    else:
        cursor = conn.cursor()
        # ตรวจสอบให้แน่ใจว่าเลือกคอลัมน์ 'position' ด้วย
        cursor.execute("SELECT id, full_name, school_affiliation, position, major_subject, teaching_subjects, contact_number, photo_path FROM teachers")
        data = cursor.fetchall()
        column_names = [description[0] for description in cursor.description]
        conn.close()
        df = pd.DataFrame(data, columns=column_names)

    df.rename(columns={
        'id': 'รหัสครู',
        'full_name': 'ชื่อ-สกุล',
        'school_affiliation': 'สังกัดโรงเรียน',
        'position': 'ตำแหน่ง', # เพิ่มชื่อคอลัมน์ตำแหน่ง
        'major_subject': 'วิชาเอก',
        'teaching_subjects': 'สอนรายวิชา',
        'contact_number': 'เบอร์ติดต่อ',
        'photo_path': 'เส้นทางไฟล์รูปภาพ'
    }, inplace=True)
    
    output = pd.ExcelWriter('teachers_data.xlsx', engine='xlsxwriter')
    df.to_excel(output, index=False, sheet_name='ข้อมูลครู')
    output.close() 

    with open('teachers_data.xlsx', 'rb') as f:
        file_data = f.read()
    os.remove('teachers_data.xlsx') 
    return file_data

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

# อัปเดตฟังก์ชันเพิ่มข้อมูลครู
def add_teacher_to_db(full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None, position=None):
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
                INSERT INTO teachers (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_path, position)
                VALUES (:full_name, :school_affiliation, :major_subject, :teaching_subjects, :contact_number, :photo_path, :position)
            ''', params=dict(
                full_name=full_name,
                school_affiliation=school_affiliation,
                major_subject=major_subject,
                teaching_subjects=teaching_subjects,
                contact_number=contact_number,
                photo_path=saved_photo_path,
                position=position # เพิ่มตำแหน่ง
            ))
            s.commit()
    else:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO teachers (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_path, position)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, saved_photo_path, position)) # เพิ่มตำแหน่ง
        conn.commit()
        conn.close()
    st.cache_data.clear()
    st.success(f"เพิ่มข้อมูลครู '{full_name}' สำเร็จ!")

# อัปเดตฟังก์ชันแก้ไขข้อมูลครู
def update_teacher_in_db(teacher_id, full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None, position=None):
    conn = get_db_connection()
    current_teacher = get_teacher_by_id_from_db(teacher_id)

    if not current_teacher:
        st.error("ไม่พบครูที่ต้องการแก้ไข")
        return False

    updates = []
    params = [] # Use a list for positional parameters

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
            updates.append("photo_path = ?")
            params.append(saved_photo_path)
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
        updates.append("photo_path = ?")
        params.append(None) # Set photo_path to NULL if cleared

    if not updates:
        st.info("ไม่มีข้อมูลที่เปลี่ยนแปลง")
        return False

    params.append(teacher_id) # Add the ID for the WHERE clause
    query = f"UPDATE teachers SET {', '.join(updates)} WHERE id = ?"
    
    if hasattr(conn, 'session'):
        # For st.connection, still use named parameters if possible for clarity,
        # or adapt to use positional parameters if st.connection also supports it.
        # For simplicity and consistency with the SQLite raw connection, we'll
        # adjust to use positional parameters here as well.
        # The key is that the 'params' dictionary for st.connection needs to match
        # the named placeholders you would use.
        # Let's revert the st.connection part to use named params as before, 
        # as it handles it well. We only change the direct sqlite3 part.
        
        # --- Original logic for st.connection (which works) ---
        named_params = {}
        idx = 0
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

        # Re-evaluate photo_path for named_params
        if photo_file:
             # Logic for saved_photo_path needs to be here to be consistent
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
                named_params['photo_path'] = None # Ensure it's handled even on error
        elif st.session_state.get('photo_cleared', False):
            named_params['photo_path'] = None # Explicitly set to None for clearing

        named_params['id'] = teacher_id
        
        # Construct the query string with named parameters for st.connection
        named_updates = []
        for key in named_params.keys():
            if key != 'id': # Don't add 'id' to the SET clause
                named_updates.append(f"{key} = :{key}")
        named_query = f"UPDATE teachers SET {', '.join(named_updates)} WHERE id = :id"

        with conn.session as s:
            s.execute(named_query, params=named_params)
            s.commit()
    else:
        # --- Modified logic for direct sqlite3 connection ---
        cursor = conn.cursor()
        cursor.execute(query, tuple(params)) # Pass parameters as a tuple
        conn.commit()
        conn.close()
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

# เพิ่ม CSS สำหรับสไตล์ Minimal (ตัวอย่าง)
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

setup_database()

# --- ส่วนหัว: ชื่อระบบและโลโก้ ---
header_container = st.container()
with header_container:
    col_text, col_logo = st.columns([5, 1])
    with col_text:
        st.markdown("## 👨‍🏫 **ระบบจัดการฐานข้อมูลครูกลุ่มโรงเรียนบ้านด่าน 2**", unsafe_allow_html=True)
    with col_logo:
        logo_path = "ban_dan_2_logo.png" 
        if os.path.exists(logo_path):
            try:
                logo = Image.open(logo_path)
                st.image(logo, width=100) 
            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการโหลดโลโก้: {e}")
        else:
            st.warning(f"ไม่พบไฟล์โลโก้ที่: {logo_path}")

st.markdown("---") 

# --- Navigation Buttons and Export ---
nav_container = st.container()
with nav_container:
    col1, col2, col3, _ = st.columns([1,1,1,3]) 
    with col1:
        if st.button("📚 แสดงข้อมูลครูทั้งหมด", key="show_all", use_container_width=True):
            st.session_state.current_view = 'list'
            st.session_state.edit_teacher_id = None
            st.session_state.photo_cleared = False
            st.session_state.search_query_school = ""
            st.rerun()
    with col2:
        if st.button("➕ เพิ่มข้อมูลครูใหม่", key="add_new", use_container_width=True):
            st.session_state.current_view = 'add'
            st.session_state.edit_teacher_id = None
            st.session_state.photo_cleared = False
            st.rerun()
    with col3:
        excel_file_data = export_teachers_to_excel()
        st.download_button(
            label="⬇️ Export ข้อมูลครู (.xlsx)", 
            data=excel_file_data,
            file_name="ข้อมูลครู_กลุ่มโรงเรียนบ้านด่าน2.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            key="download_excel_button",
            use_container_width=True
        )

st.markdown("---") 

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
                st.write("") 
                if st.button("ค้นหา", key="search_button", use_container_width=True):
                    st.session_state.search_query_school = search_term
        
        st.markdown("<br>", unsafe_allow_html=True) 

        teachers = get_all_teachers_from_db_cached()
        
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
            for teacher in teachers_to_display: 
                teacher_card = st.container(border=True) 
                with teacher_card:
                    col_left, col_right = st.columns([2, 1])
                    with col_left:
                        st.markdown(f"### {teacher['full_name']} (ID: {teacher['id']})")
                        st.markdown(f"**ตำแหน่ง:** {teacher.get('position', '-') or '-'}") # แสดงตำแหน่ง
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
                    
                        st.markdown("<br>", unsafe_allow_html=True) 
                        edit_button = st.button(f"✏️ แก้ไข", key=f"edit_teacher_{teacher['id']}", use_container_width=True)
                        delete_button = st.button(f"🗑️ ลบ", key=f"delete_teacher_{teacher['id']}", use_container_width=True)
                        
                        if edit_button:
                            st.session_state.current_view = 'edit'
                            st.session_state.edit_teacher_id = teacher['id']
                            st.rerun()
                        
                        if delete_button:
                            if st.session_state.get(f'confirm_delete_{teacher["id"]}', False):
                                if st.button("ยืนยันการลบ", key=f"confirm_delete_final_{teacher['id']}", type="primary", use_container_width=True):
                                    if delete_teacher_from_db(teacher['id']):
                                        st.session_state.current_view = 'list'
                                    del st.session_state[f'confirm_delete_{teacher["id"]}']
                                    st.rerun()
                            else:
                                st.session_state[f'confirm_delete_{teacher["id"]}'] = True
                                st.warning(f"คลิก 'ยืนยันการลบ' เพื่อลบ '{teacher['full_name']}'")
                st.markdown("<br>", unsafe_allow_html=True) 

        else:
            st.info("ไม่พบข้อมูลครูในระบบ หรือไม่พบผลการค้นหา")

    elif st.session_state.current_view == 'add':
        st.header("เพิ่มข้อมูลครูใหม่")
        with st.form("add_teacher_form", clear_on_submit=True):
            full_name = st.text_input("ชื่อ-สกุล:", key="add_full_name")
            position = st.text_input("ตำแหน่ง:", key="add_position", placeholder="เช่น ครูผู้ช่วย, ครูชำนาญการ") # เพิ่มช่องตำแหน่ง
            school_affiliation = st.text_input("สังกัดโรงเรียน:", key="add_school_affiliation")
            major_subject = st.text_input("วิชาเอก:", key="add_major_subject")
            teaching_subjects = st.text_input("สอนรายวิชา (คั่นด้วยคอมม่า):", key="add_teaching_subjects")
            contact_number = st.text_input("เบอร์ติดต่อ:", key="add_contact_number")
            photo_file = st.file_uploader("รูปถ่ายใบหน้า:", type=["png", "jpg", "jpeg"], key="add_photo_uploader")

            submitted = st.form_submit_button("💾 บันทึกข้อมูลครู", type="primary")
            if submitted:
                if full_name:
                    add_teacher_to_db(full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file, position) # ส่งค่าตำแหน่ง
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
                    new_full_name = st.text_input("ชื่อ-สกุล:", value=teacher_data['full_name'] or "", key="edit_full_name")
                    new_position = st.text_input("ตำแหน่ง:", value=teacher_data.get('position', '') or "", key="edit_position") # แสดงค่าตำแหน่งเดิม
                    new_school_affiliation = st.text_input("สังกัดโรงเรียน:", value=teacher_data['school_affiliation'] or "", key="edit_school_affiliation")
                    new_major_subject = st.text_input("วิชาเอก:", value=teacher_data['major_subject'] or "", key="edit_major_subject")
                    new_teaching_subjects = st.text_input("สอนรายวิชา (คั่นด้วยคอมม่า):", value=teacher_data['teaching_subjects'] or "", key="edit_teaching_subjects")
                    new_contact_number = st.text_input("เบอร์ติดต่อ:", value=teacher_data['contact_number'] or "", key="edit_contact_number")

                    if teacher_data['photo_path']:
                        photo_path_full = os.path.join(UPLOAD_FOLDER, teacher_data['photo_path'])
                        if os.path.exists(photo_path_full):
                            st.image(photo_path_full, caption="รูปภาพปัจจุบัน", width=150)
                        else:
                            st.warning("ไม่พบไฟล์รูปภาพปัจจุบันในโฟลเดอร์")
                    else:
                        st.info("ยังไม่มีรูปภาพสำหรับครูคนนี้")

                    new_photo_file = st.file_uploader("เปลี่ยนรูปถ่ายใบหน้า (เลือกไฟล์ใหม่):", type=["png", "jpg", "jpeg"], key="edit_photo_uploader")
                    
                    clear_photo = st.checkbox("ลบรูปภาพปัจจุบัน", value=st.session_state.get('photo_cleared', False), key="clear_current_photo")
                    st.session_state.photo_cleared = clear_photo

                    submitted = st.form_submit_button("📝 บันทึกการแก้ไข", type="primary")
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
                                photo_to_save,
                                new_position # ส่งค่าตำแหน่ง
                            ):
                                st.session_state.current_view = 'list'
                                st.session_state.edit_teacher_id = None
                                st.session_state.photo_cleared = False
                                st.rerun()
            else:
                st.error("ไม่พบข้อมูลครูที่ต้องการแก้ไข")
                st.session_state.current_view = 'list'
                st.rerun()
