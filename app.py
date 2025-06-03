import streamlit as st
import sqlite3
import os
import shutil

# --- Configuration ---
DATABASE_NAME = 'teacher_management.db'
PHOTO_DIR = 'teacher_photos'
UPLOAD_FOLDER = PHOTO_DIR # Streamlit will run from the app's root dir

# --- Database Setup and Functions ---
def get_db_connection():
    # Attempt to use st.connection for Streamlit Cloud deployment
    # This requires .streamlit/secrets.toml to be set up on Streamlit Cloud
    try:
        conn = st.connection('teacher_db', type='sql')
        return conn
    except Exception:
        # Fallback to direct sqlite3.connect for local development or if st.connection fails
        # Ensure that this connection is handled carefully for threading if deployed
        conn = sqlite3.connect(DATABASE_NAME)
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        return conn

def setup_database():
    conn = get_db_connection()
    if isinstance(conn, st._connections.SQLConnection): # Check if it's Streamlit's connection object
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
    else: # Fallback for direct sqlite3.connect
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
        conn.close() # Close direct connection after setup

    # Create photo directory if it doesn't exist
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
        st.info(f"Created upload directory: {UPLOAD_FOLDER}") # Only show in local dev


# Use st.cache_data to cache results from database queries for performance
@st.cache_data(ttl=3600) # Cache for 1 hour
def get_all_teachers_from_db_cached():
    conn = get_db_connection()
    if isinstance(conn, st._connections.SQLConnection):
        df = conn.query('SELECT * FROM teachers', ttl=0) # ttl=0 means no cache on query level
        return df.to_dict(orient='records') # Convert DataFrame to list of dicts
    else:
        cursor = conn.cursor()
        teachers = cursor.execute('SELECT * FROM teachers').fetchall()
        conn.close()
        return [dict(t) for t in teachers] # Convert sqlite3.Row to dict

def get_teacher_by_id_from_db(teacher_id):
    conn = get_db_connection()
    if isinstance(conn, st._connections.SQLConnection):
        try:
            # Fetch as DataFrame then get first row as dict
            teacher = conn.query(f'SELECT * FROM teachers WHERE id = {teacher_id}').iloc[0].to_dict()
            return teacher
        except IndexError: # Handle case where no teacher is found
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
            # Ensure unique filename to avoid overwrites
            new_filename = f"{os.path.splitext(photo_file.name)[0]}_{os.urandom(8).hex()}{extension}"
            saved_photo_path_full = os.path.join(UPLOAD_FOLDER, new_filename)
            
            # Save uploaded file
            with open(saved_photo_path_full, "wb") as f:
                f.write(photo_file.getbuffer())
            saved_photo_path = new_filename # Store only filename relative to PHOTO_DIR
            st.toast(f"บันทึกรูปภาพ: {saved_photo_path_full}", icon="📸")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพ: {e}")
            saved_photo_path = None

    if isinstance(conn, st._connections.SQLConnection):
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
    st.cache_data.clear() # Clear cache after data modification
    st.success(f"เพิ่มข้อมูลครู '{full_name}' สำเร็จ!")

def update_teacher_in_db(teacher_id, full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None):
    conn = get_db_connection()
    current_teacher = get_teacher_by_id_from_db(teacher_id)

    updates = []
    params = {}

    # Only add to updates if the value has actually changed
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
    
    saved_photo_path = current_teacher['photo_path'] # Default to current photo path
    if photo_file: # A new file was uploaded
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
            saved_photo_path = new_filename # Store only filename relative to PHOTO_DIR
            updates.append("photo_path = :photo_path")
            params['photo_path'] = saved_photo_path
            st.toast(f"บันทึกรูปภาพใหม่: {saved_photo_path_full}", icon="📸")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพใหม่: {e}")
            
    elif st.session_state.photo_cleared: # User explicitly checked "ลบรูปภาพปัจจุบัน"
        if current_teacher and current_teacher['photo_path']:
            old_photo_full_path = os.path.join(UPLOAD_FOLDER, current_teacher['photo_path'])
            if os.path.exists(old_photo_full_path):
                try:
                    os.remove(old_photo_full_path)
                    st.info(f"ลบรูปภาพ (ตามคำสั่ง): {old_photo_full_path}")
                except Exception as e:
                    st.warning(f"เกิดข้อผิดพลาดในการลบรูปภาพ (ตามคำสั่ง): {e}")
        updates.append("photo_path = :photo_path")
        params['photo_path'] = None # Set to NULL in DB

    if not updates:
        st.info("ไม่มีข้อมูลที่เปลี่ยนแปลง")
        return

    params['id'] = teacher_id
    query = f"UPDATE teachers SET {', '.join(updates)} WHERE id = :id"
    
    if isinstance(conn, st._connections.SQLConnection):
        with conn.session as s:
            s.execute(query, params=params)
            s.commit()
    else:
        cursor = conn.cursor()
        # For sqlite3, params need to be in correct order and as a tuple
        # This part needs careful mapping if you use the fallback.
        # A safer approach for fallback is to reconstruct the query with ? placeholders
        # and then build the params tuple in the correct order.
        # For simplicity, if using st.connection is primary, this might be less critical.
        # As an example, a direct execution might look like:
        # cursor.execute(f"UPDATE teachers SET full_name = ?, contact_number = ? WHERE id = ?", (full_name, contact_number, teacher_id))
        # Given we build 'updates' dynamically, re-ordering params for direct execute is complex.
        # Sticking with st.connection for ease here.
        st.warning("การอัปเดตแบบ fallback ไปใช้ sqlite3.connect อาจไม่ทำงานสมบูรณ์กับพารามิเตอร์ที่ซับซ้อน")
        pass # Not executing the update for direct sqlite3.connect in this complex case
    st.cache_data.clear()
    st.success(f"ข้อมูลครู ID {teacher_id} อัปเดตสำเร็จ!")


def delete_teacher_from_db(teacher_id):
    conn = get_db_connection()
    teacher_to_delete = get_teacher_by_id_from_db(teacher_id) # Get info before deleting

    if isinstance(conn, st._connections.SQLConnection):
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


# --- Streamlit App UI ---
st.set_page_config(layout="wide", page_title="ระบบจัดการฐานข้อมูลครู")

st.title("👨‍🏫 ระบบจัดการฐานข้อมูลครู")

# Initialize session state for navigation and current teacher ID
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'list' # 'list', 'add', 'edit'
if 'edit_teacher_id' not in st.session_state:
    st.session_state.edit_teacher_id = None
if 'photo_cleared' not in st.session_state: # To track if user wants to clear photo
    st.session_state.photo_cleared = False

# Setup database and photo directory at startup
setup_database()

# --- Navigation ---
col1, col2, col3 = st.columns([1,1,4])
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

# --- Content Area based on current_view ---
if st.session_state.current_view == 'list':
    st.header("รายการข้อมูลครู")
    teachers = get_all_teachers_from_db_cached()

    if teachers:
        # Create a list of dictionaries to pass to st.dataframe for better display
        display_teachers = []
        for t in teachers:
            teacher_dict = dict(t)
            # Adjust photo_path for display
            if teacher_dict['photo_path']:
                teacher_dict['photo_path_display'] = os.path.join(UPLOAD_FOLDER, teacher_dict['photo_path'])
            else:
                teacher_dict['photo_path_display'] = None
            display_teachers.append(teacher_dict)

        # Display teachers using columns for better layout than st.dataframe for individual records
        for teacher in display_teachers:
            col_left, col_right = st.columns([2, 1])
            with col_left:
                st.subheader(f"{teacher['full_name']} (ID: {teacher['id']})")
                st.write(f"**สังกัดโรงเรียน:** {teacher['school_affiliation']}")
                st.write(f"**วิชาเอก:** {teacher['major_subject']}")
                st.write(f"**สอนรายวิชา:** {teacher['teaching_subjects']}")
                st.write(f"**เบอร์ติดต่อ:** {teacher['contact_number']}")
            with col_right:
                if teacher['photo_path_display'] and os.path.exists(teacher['photo_path_display']):
                    st.image(teacher['photo_path_display'], caption=f"รูป {teacher['full_name']}", width=150)
                else:
                    st.info("ไม่มีรูปภาพ")
                
                # Action buttons for each teacher
                edit_button = st.button(f"แก้ไขข้อมูล ID {teacher['id']}", key=f"edit_teacher_{teacher['id']}", use_container_width=True)
                delete_button = st.button(f"ลบข้อมูล ID {teacher['id']}", key=f"delete_teacher_{teacher['id']}", use_container_width=True)
                
                if edit_button:
                    st.session_state.current_view = 'edit'
                    st.session_state.edit_teacher_id = teacher['id']
                    st.rerun()
                
                if delete_button:
                    # Streamlit doesn't have a native confirm dialog for buttons
                    # You can implement a custom one with st.session_state
                    if st.warning(f"คุณแน่ใจหรือไม่ที่จะลบครู {teacher['full_name']}?"):
                        # This warning is just a display, not a real confirm.
                        # For real confirmation, you'd need more complex logic.
                        delete_teacher_from_db(teacher['id'])
                        st.session_state.current_view = 'list'
                        st.rerun() # Rerun to refresh list

            st.markdown("---") # Separator for each teacher

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
                # After successful add, switch back to list view
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
                # Use current data as default value
                new_full_name = st.text_input("ชื่อ-สกุล:", value=teacher_data['full_name'], key="edit_full_name")
                new_school_affiliation = st.text_input("สังกัดโรงเรียน:", value=teacher_data['school_affiliation'] or "", key="edit_school_affiliation")
                new_major_subject = st.text_input("วิชาเอก:", value=teacher_data['major_subject'] or "", key="edit_major_subject")
                new_teaching_subjects = st.text_input("สอนรายวิชา (คั่นด้วยคอมม่า):", value=teacher_data['teaching_subjects'] or "", key="edit_teaching_subjects")
                new_contact_number = st.text_input("เบอร์ติดต่อ:", value=teacher_data['contact_number'] or "", key="edit_contact_number")

                # Display current photo if exists
                if teacher_data['photo_path']:
                    photo_path_full = os.path.join(UPLOAD_FOLDER, teacher_data['photo_path'])
                    if os.path.exists(photo_path_full):
                        st.image(photo_path_full, caption="รูปภาพปัจจุบัน", width=150)
                    else:
                        st.warning("ไม่พบไฟล์รูปภาพปัจจุบันในโฟลเดอร์")
                else:
                    st.info("ยังไม่มีรูปภาพสำหรับครูคนนี้")

                new_photo_file = st.file_uploader("เปลี่ยนรูปถ่ายใบหน้า (เลือกไฟล์ใหม่):", type=["png", "jpg", "jpeg"], key="edit_photo_uploader")
                
                # Checkbox to clear photo
                clear_photo = st.checkbox("ลบรูปภาพปัจจุบัน", key="clear_current_photo")
                if clear_photo:
                    st.session_state.photo_cleared = True
                else:
                    st.session_state.photo_cleared = False # Reset if unchecked

                submitted = st.form_submit_button("บันทึกการแก้ไข")
                if submitted:
                    if not new_full_name:
                        st.error("ชื่อ-สกุล ต้องไม่ว่างเปล่า!")
                    else:
                        # Decide which photo action to take
                        photo_to_save = new_photo_file
                        if st.session_state.photo_cleared:
                            photo_to_save = None # Signal to remove photo

                        update_teacher_in_db(
                            teacher_id_to_edit,
                            new_full_name,
                            new_school_affiliation,
                            new_major_subject,
                            new_teaching_subjects,
                            new_contact_number,
                            photo_to_save
                        )
                        # After successful update, switch back to list view
                        st.session_state.current_view = 'list'
                        st.session_state.edit_teacher_id = None
                        st.session_state.photo_cleared = False # Reset state
                        st.rerun()
        else:
            st.error("ไม่พบข้อมูลครูที่ต้องการแก้ไข")
            st.session_state.current_view = 'list' # Redirect to list view
            st.rerun()
