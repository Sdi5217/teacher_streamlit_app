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
    """
    Attempts to get a Streamlit SQL connection if configured via st.secrets.
    Falls back to a direct sqlite3.connect for local development or if not configured.
    """
    try:
        # Check if st.secrets is available and has connection info for 'teacher_db'
        # This is the most reliable way to check if st.connection is configured for deployment.
        if "connections" in st.secrets and "teacher_db" in st.secrets["connections"]:
            return st.connection('teacher_db', type='sql')
    except Exception:
        # Pass silently if st.secrets or connection fails, will fall back to sqlite3.connect
        pass

    # Fallback for local development or if st.connection is not configured on Streamlit Cloud
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row # Allows accessing columns by name
    return conn

def setup_database():
    """
    Sets up the teachers table in the database and ensures the photo upload directory exists.
    Handles both Streamlit connection and direct sqlite3 connection.
    """
    conn = get_db_connection()
    
    # Check if 'conn' has a '.session' attribute (typical for st.connection objects)
    # This is a safer way to differentiate than checking internal _connections attribute.
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
        # No need to close conn if it's a st.connection object, as Streamlit manages it
    else: # This is a direct sqlite3.connect object
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
        # st.info(f"Created upload directory: {UPLOAD_FOLDER}") # Can be commented out for production
    
# Use st.cache_data to cache results from database queries for performance
@st.cache_data(ttl=3600) # Cache for 1 hour to prevent excessive database reads
def get_all_teachers_from_db_cached():
    """
    Fetches all teacher records from the database. Caches results.
    """
    conn = get_db_connection()
    if hasattr(conn, 'session'): # If it's a Streamlit SQL connection
        df = conn.query('SELECT * FROM teachers', ttl=0) # ttl=0 means no cache on query level
        return df.to_dict(orient='records') # Convert DataFrame to list of dicts for consistent output
    else: # If it's a direct sqlite3 connection
        cursor = conn.cursor()
        teachers = cursor.execute('SELECT * FROM teachers').fetchall()
        conn.close()
        return [dict(t) for t in teachers] # Convert sqlite3.Row to dict

def get_teacher_by_id_from_db(teacher_id):
    """
    Fetches a single teacher record by ID.
    """
    conn = get_db_connection()
    if hasattr(conn, 'session'): # If it's a Streamlit SQL connection
        try:
            teacher = conn.query(f'SELECT * FROM teachers WHERE id = {teacher_id}', ttl=0).iloc[0].to_dict()
            return teacher
        except IndexError: # Handle case where no teacher is found
            return None
    else: # If it's a direct sqlite3 connection
        cursor = conn.cursor()
        teacher = cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,)).fetchone()
        conn.close()
        return dict(teacher) if teacher else None

def add_teacher_to_db(full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None):
    """
    Adds a new teacher record to the database, including saving photo file if provided.
    """
    conn = get_db_connection()
    saved_photo_path = None
    if photo_file:
        try:
            extension = os.path.splitext(photo_file.name)[1]
            new_filename = f"{os.path.splitext(photo_file.name)[0]}_{os.urandom(8).hex()}{extension}"
            saved_photo_path_full = os.path.join(UPLOAD_FOLDER, new_filename)
            
            with open(saved_photo_path_full, "wb") as f:
                f.write(photo_file.getbuffer())
            saved_photo_path = new_filename # Store only filename relative to PHOTO_DIR
            st.toast(f"บันทึกรูปภาพ: {saved_photo_path_full}", icon="📸")
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการบันทึกรูปภาพ: {e}")
            saved_photo_path = None

    if hasattr(conn, 'session'): # If it's a Streamlit SQL connection
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
    else: # If it's a direct sqlite3 connection
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO teachers (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_path)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (full_name, school_affiliation, major_subject, teaching_subjects, contact_number, saved_photo_path))
        conn.commit()
        conn.close()
    st.cache_data.clear() # Clear cache after data modification to ensure fresh data on next fetch
    st.success(f"เพิ่มข้อมูลครู '{full_name}' สำเร็จ!")

def update_teacher_in_db(teacher_id, full_name, school_affiliation, major_subject, teaching_subjects, contact_number, photo_file=None):
    """
    Updates an existing teacher record in the database.
    Handles photo updates (add new, replace old, or clear).
    """
    conn = get_db_connection()
    current_teacher = get_teacher_by_id_from_db(teacher_id) # Get current data for comparison and old photo path

    if not current_teacher:
        st.error("ไม่พบครูที่ต้องการแก้ไข")
        return False

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
    
    # Handle photo updates
    if photo_file: # A new file was uploaded
        if current_teacher and current_teacher['photo_path']: # Delete old photo if it exists
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
            
    elif st.session_state.get('photo_cleared', False): # User explicitly checked "ลบรูปภาพปัจจุบัน"
        if current_teacher and current_teacher['photo_path']: # Delete current photo file
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
        return False

    params['id'] = teacher_id
    query = f"UPDATE teachers SET {', '.join(updates)} WHERE id = :id"
    
    if hasattr(conn, 'session'): # If it's a Streamlit SQL connection
        with conn.session as s:
            s.execute(query, params=params)
            s.commit()
    else: # If it's a direct sqlite3 connection (less robust for dynamic updates)
        cursor = conn.cursor()
        # For direct sqlite3, you need to ensure parameters are ordered correctly or use string formatting (less safe)
        # Given the dynamic nature of 'updates' and 'params', this fallback is not fully robust for sqlite3 direct.
        # It's highly recommended to use st.connection for database operations in Streamlit.
        st.error("การอัปเดตข้อมูลผ่าน SQLite โดยตรงไม่รองรับการอัปเดตแบบไดนามิกหลายฟิลด์อย่างสมบูรณ์ด้วยวิธีการนี้")
        conn.close() # Close direct connection
        return False
    st.cache_data.clear() # Clear cache after data modification
    st.success(f"ข้อมูลครู ID {teacher_id} อัปเดตสำเร็จ!")
    return True

def delete_teacher_from_db(teacher_id):
    """
    Deletes a teacher record and associated photo file from the database and disk.
    """
    conn = get_db_connection()
    teacher_to_delete = get_teacher_by_id_from_db(teacher_id) # Get info before deleting for photo path

    if not teacher_to_delete:
        st.error(f"ไม่พบครู ID {teacher_id} ที่ต้องการลบ")
        return False

    if hasattr(conn, 'session'): # If it's a Streamlit SQL connection
        with conn.session as s:
            s.execute('DELETE FROM teachers WHERE id = :id', params=dict(id=teacher_id))
            s.commit()
    else: # If it's a direct sqlite3 connection
        cursor = conn.cursor()
        cursor.execute('DELETE FROM teachers WHERE id = ?', (teacher_id,))
        conn.commit()
        conn.close()

    if teacher_to_delete and teacher_to_delete['photo_path']: # Delete the photo file if it exists
        photo_full_path = os.path.join(UPLOAD_FOLDER, teacher_to_delete['photo_path'])
        if os.path.exists(photo_full_path):
            try:
                os.remove(photo_full_path)
                st.info(f"ลบรูปภาพ: {photo_full_path}")
            except Exception as e:
                st.warning(f"เกิดข้อผิดพลาดในการลบไฟล์รูปภาพ: {e}")
    st.cache_data.clear() # Clear cache after data modification
    st.success(f"ข้อมูลครู ID {teacher_id} ถูกลบสำเร็จ!")
    return True

# --- Streamlit App UI ---
st.set_page_config(layout="wide", page_title="ระบบจัดการฐานข้อมูลครู")

st.title("👨‍🏫 ระบบจัดการฐานข้อมูลครู")

# Initialize session state for navigation and current teacher ID
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'list' # 'list', 'add', 'edit'
if 'edit_teacher_id' not in st.session_state:
    st.session_state.edit_teacher_id = None
if 'photo_cleared' not in st.session_state: # To track if user wants to clear photo during edit
    st.session_state.photo_cleared = False

# Setup database and photo directory at startup
setup_database()

# --- Navigation Buttons ---
col1, col2, _ = st.columns([1,1,4]) # Use _ for the third column to discard it
with col1:
    if st.button("แสดงข้อมูลครูทั้งหมด", key="show_all", use_container_width=True):
        st.session_state.current_view = 'list'
        st.session_state.edit_teacher_id = None
        st.session_state.photo_cleared = False
        st.rerun() # Rerun to switch view immediately
with col2:
    if st.button("เพิ่มข้อมูลครูใหม่", key="add_new", use_container_width=True):
        st.session_state.current_view = 'add'
        st.session_state.edit_teacher_id = None
        st.session_state.photo_cleared = False
        st.rerun() # Rerun to switch view immediately

st.markdown("---") # Horizontal line for separation

# --- Content Area based on current_view ---
if st.session_state.current_view == 'list':
    st.header("รายการข้อมูลครู")
    teachers = get_all_teachers_from_db_cached()

    if teachers:
        # Display teachers using columns for better layout than st.dataframe for individual records
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
                    if os.path.exists(photo_path_full): # Check if file actually exists on disk
                        st.image(photo_path_full, caption=f"รูป {teacher['full_name']}", width=150)
                    else:
                        st.warning("ไม่พบไฟล์รูปภาพ") # Warn if path exists in DB but file doesn't
                else:
                    st.info("ไม่มีรูปภาพ")
                
                # Action buttons for each teacher, using unique keys
                edit_button = st.button(f"แก้ไข ID {teacher['id']}", key=f"edit_teacher_{teacher['id']}", use_container_width=True)
                delete_button = st.button(f"ลบ ID {teacher['id']}", key=f"delete_teacher_{teacher['id']}", use_container_width=True)
                
                if edit_button:
                    st.session_state.current_view = 'edit'
                    st.session_state.edit_teacher_id = teacher['id']
                    st.rerun()
                
                if delete_button:
                    # Implement a simple confirmation dialog using session state
                    if st.session_state.get(f'confirm_delete_{teacher["id"]}', False):
                        delete_teacher_from_db(teacher['id'])
                        st.session_state.current_view = 'list'
                        del st.session_state[f'confirm_delete_{teacher["id"]}'] # Clear confirmation state
                        st.rerun()
                    else:
                        st.session_state[f'confirm_delete_{teacher["id"]}'] = True
                        st.warning(f"คลิก 'ลบ ID {teacher['id']}' อีกครั้งเพื่อยืนยันการลบ '{teacher['full_name']}'")

            st.markdown("---") # Separator for each teacher record

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
                st.session_state.current_view = 'list' # After successful add, switch back to list view
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
                # Use current data as default value for text inputs
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
                
                # Checkbox to clear photo. Reset photo_cleared state when form is re-rendered if not explicitly checked.
                clear_photo = st.checkbox("ลบรูปภาพปัจจุบัน", value=st.session_state.photo_cleared, key="clear_current_photo")
                st.session_state.photo_cleared = clear_photo # Update session state based on checkbox value

                submitted = st.form_submit_button("บันทึกการแก้ไข")
                if submitted:
                    if not new_full_name:
                        st.error("ชื่อ-สกุล ต้องไม่ว่างเปล่า!")
                    else:
                        # Decide which photo action to take
                        photo_to_save = new_photo_file # Default: use newly uploaded file
                        if st.session_state.photo_cleared:
                            photo_to_save = None # Signal to remove photo if checkbox is checked

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
                            st.session_state.photo_cleared = False # Reset state after update
                            st.rerun()
        else:
            st.error("ไม่พบข้อมูลครูที่ต้องการแก้ไข")
            st.session_state.current_view = 'list' # Redirect to list view
            st.rerun()
