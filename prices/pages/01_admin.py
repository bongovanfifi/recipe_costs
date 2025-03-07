import streamlit as st
from sqlalchemy import text
import sys
from pathlib import Path
import datetime as dt

sys.path.append(str(Path(__file__).parent.parent))
import shared.utils as u
import time


# TODO: This is a bad way of authenticating. A week or two after I added it, streamlit added st.login(), but at time of writing it's still in the expiremental phase. Replace all this dumb sqlite stuff with st.login() when it's stable.
def check_admin_password():
    """Check if user has admin password with persistent rate limiting"""
    if st.session_state.get("admin_authenticated"):
        return True
    ip = st.query_params.get("client_ip", ["unknown"])[0]
    with u.get_local_connection().session as session:
        lockout = session.execute(
            text("SELECT attempts, last_attempt FROM lockouts WHERE ip = :ip"),
            {"ip": ip},
        ).fetchone()
        current_time = int(dt.datetime.now().timestamp())
        if lockout and lockout.attempts >= 10:
            if current_time - lockout.last_attempt < 300:
                st.error("Too many attempts. Please wait 5 minutes.")
                time.sleep(2)
                return False
            else:
                session.execute(
                    text("UPDATE lockouts SET attempts = 0 WHERE ip = :ip"), {"ip": ip}
                )
                session.commit()

    with st.form("admin_login", clear_on_submit=True):
        password = st.text_input("Admin Password", type="password", key="pwd")
        submitted = st.form_submit_button("Login")

        if submitted:
            if password == st.secrets.passwords.admin:
                st.session_state.admin_authenticated = True
                st.rerun()
                return True
            else:
                with u.get_local_connection().session as session:
                    session.execute(
                        text(
                            """
                            INSERT INTO lockouts (ip, attempts, last_attempt) 
                            VALUES (:ip, 1, :time)
                            ON CONFLICT(ip) DO UPDATE SET 
                            attempts = attempts + 1,
                            last_attempt = :time
                        """
                        ),
                        {"ip": ip, "time": current_time},
                    )
                    session.commit()
                st.error("Incorrect password")
                time.sleep(1)
                return False

    return False


if not check_admin_password():
    st.stop()

db = u.get_db("prices")

ingredients = db.get_all_ingredients()
if ingredients.empty:
    st.error("No ingredients found.")
    st.stop()
ingredients = u.get_new_entries(ingredients, ["id"])

st.title("Ingredient Administration")

st.subheader("Add Ingredient")
st.write(
    "You may want to Rename an ingredient instead. New ingredients will not automatically be used in the recipes, even if the name is the same."
)

with st.form("add_ingredient", clear_on_submit=True):
    name = st.text_input("Name")
    submitted = st.form_submit_button("Add")
    if submitted:
        if not ingredients.empty and name in ingredients["name"].values:
            st.error(f"""Ingredient named "{name}" already exists.""")
        else:
            try:
                db.put_ingredient(name)
                st.session_state.success_message_add = f"Added {name}"
                st.rerun()
            except Exception as e:
                st.error(f"Update failed: {e}")
    if "success_message_add" in st.session_state:
        st.success(st.session_state.success_message_add)
        del st.session_state.success_message_add

if ingredients.empty:
    st.error("No ingredients found.")
    st.stop()

st.subheader("Rename Ingredient")

ingredient_id = st.selectbox(
    "Select Ingredient",
    options=ingredients["id"].tolist(),
    format_func=lambda id: ingredients[ingredients["id"] == id]["name"].iloc[0],
)

with st.form("rename_ingredient", clear_on_submit=True):
    selected_ingredient = ingredients[ingredients["id"] == ingredient_id].iloc[0]
    if selected_ingredient.any():
        new_name = st.text_input("New Name", selected_ingredient["name"])
    if st.form_submit_button("Update"):
        if not new_name:
            st.error("New Name can't be blank.")
        elif new_name in ingredients["name"].values:
            st.error(f"""Ingredient named "{new_name}" already exists.""")
        else:
            try:
                db.update_ingredient(
                    ingredient_id,
                    name=new_name,
                )
                st.session_state.success_message_rename = f"Updated {new_name}"
                st.rerun()
            except Exception as e:
                st.error(f"Update failed: {e}")
    if "success_message_rename" in st.session_state:
        st.success(st.session_state.success_message_rename)
        del st.session_state.success_message_rename


st.subheader("Current Ingredients")
u.display_df(ingredients)

st.write(
    "I'll add deletion later. It causes a lot of annoying little problems with the recipe builder / cost calculator."
)
