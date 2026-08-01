import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
import os
from datetime import datetime
from PIL import Image
import numpy as np

# -----------------------------------------------------------------------------
# Configuration & Setup
# -----------------------------------------------------------------------------
st.set_page_config(page_title="FMCG Live Survey", layout="wide")

MASTER_FILE_PATH = "master_questions.xlsx"
SURVEY_FILE = "survey_responses.xlsx"
IMAGE_FOLDER = "survey_images"

if not os.path.exists(IMAGE_FOLDER):
    os.makedirs(IMAGE_FOLDER)

if "surveys_completed" not in st.session_state:
    st.session_state.surveys_completed = set()

if "selected_outlet" not in st.session_state:
    st.session_state.selected_outlet = None

# Load Saved Completed Surveys
def load_survey_data():
    if os.path.exists(SURVEY_FILE):
        try:
            return pd.read_excel(SURVEY_FILE)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

saved_responses_df = load_survey_data()
if not saved_responses_df.empty:
    col_out = next((c for c in saved_responses_df.columns if "OUTLET" in c.upper()), None)
    if col_out:
        st.session_state.surveys_completed = set(saved_responses_df[col_out].dropna().astype(str).tolist())

def save_survey_data(data_dict):
    df_new = pd.DataFrame([data_dict])
    if os.path.exists(SURVEY_FILE):
        try:
            df_old = pd.read_excel(SURVEY_FILE)
            df_final = pd.concat([df_old, df_new], ignore_index=True)
        except Exception:
            df_final = df_new
    else:
        df_final = df_new
    df_final.to_excel(SURVEY_FILE, index=False)

def calculate_distance_km(lat1, lon1, lat2, lon2):
    try:
        R = 6371.0
        lat1, lon1, lat2, lon2 = map(np.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0)**2
        c = 2 * np.arcsin(np.sqrt(a))
        return R * c
    except Exception:
        return 9999.0

# -----------------------------------------------------------------------------
# Automatic Mode Selection via URL Parameter
# -----------------------------------------------------------------------------
query_params = st.query_params
url_mode = query_params.get("mode", "admin")  # Default mode: admin

# Sidebar Mode Radio (Only visible in Admin View)
if url_mode == "surveyor":
    app_mode = "📱 Surveyor Mode (Mobile)"
else:
    st.sidebar.title("🎛️ Admin Control Panel")
    app_mode = st.sidebar.radio(
        "Select Mode:",
        ["🖥️ Admin Dashboard (Laptop Live)", "📱 Surveyor Mode Preview"]
    )

# Live GPS Capture
loc = get_geolocation()
surveyor_lat, surveyor_lon = None, None

if loc and 'coords' in loc:
    surveyor_lat = float(loc['coords']['latitude'])
    surveyor_lon = float(loc['coords']['longitude'])
    if url_mode != "surveyor":
        st.sidebar.success(f"GPS Active: {surveyor_lat:.4f}, {surveyor_lon:.4f}")

active_file = MASTER_FILE_PATH if os.path.exists(MASTER_FILE_PATH) else None

if active_file:
    try:
        excel_file = pd.ExcelFile(active_file)
        sheet_names = excel_file.sheet_names

        he_sheet_name = next((s for s in sheet_names if "HE" in s or "Hunter" in s), sheet_names[0])
        outlets_sheet_name = next((s for s in sheet_names if "Group" in s or "Outlet" in s), sheet_names[1] if len(sheet_names)>1 else sheet_names[0])

        df_he = pd.read_excel(excel_file, sheet_name=he_sheet_name)
        df_outlets = pd.read_excel(excel_file, sheet_name=outlets_sheet_name)

        df_he_columns = [str(c).strip() for c in df_he.columns]
        df_outlets.columns = df_outlets.columns.str.strip()

        master_dropdowns = {}
        for s_name in sheet_names:
            s_df = pd.read_excel(excel_file, sheet_name=s_name)
            s_df.columns = s_df.columns.str.strip()
            for col in s_df.columns:
                clean_col = col.strip()
                vals = s_df[col].dropna().astype(str).str.strip().tolist()
                if vals:
                    master_dropdowns[clean_col] = vals
                    master_dropdowns[s_name.strip()] = vals

        hunter_col = next((c for c in df_outlets.columns if "HUNTER" in c.upper() or "SURVEYOR" in c.upper()), "Hunter Name")
        hunter_list = df_outlets[hunter_col].dropna().astype(str).unique().tolist() if hunter_col in df_outlets.columns else []

        def extract_coords(row):
            loc_val = row.get("EDS Id Location", "")
            if pd.notna(loc_val):
                try:
                    parts = str(loc_val).split(",")
                    return float(parts[0].strip()), float(parts[1].strip())
                except:
                    pass
            return None, None

        df_outlets['out_lat'], df_outlets['out_lon'] = zip(*df_outlets.apply(extract_coords, axis=1))
        outlet_col = next((c for c in df_outlets.columns if "OUTLET" in c.upper()), df_outlets.columns[0])

        # =====================================================================
        # MODE 1: SURVEYOR MOBILE MODE (Clean view for field staff)
        # =====================================================================
        if url_mode == "surveyor" or app_mode == "📱 Surveyor Mode Preview":
            st.title("📱 FMCG Field Survey Portal")

            selected_hunter = st.selectbox("👤 Select Your Name (Surveyor)", options=hunter_list)

            if selected_hunter:
                df_filtered_outlets = df_outlets[df_outlets[hunter_col].astype(str) == selected_hunter].copy()
            else:
                df_filtered_outlets = df_outlets.copy()

            if surveyor_lat and surveyor_lon:
                df_filtered_outlets['distance_km'] = df_filtered_outlets.apply(
                    lambda r: calculate_distance_km(surveyor_lat, surveyor_lon, r['out_lat'], r['out_lon']), axis=1
                )
                df_filtered_outlets = df_filtered_outlets.sort_values(by='distance_km').reset_index(drop=True)

            outlet_list = df_filtered_outlets[outlet_col].dropna().astype(str).unique().tolist()

            if st.session_state.selected_outlet not in outlet_list and len(outlet_list) > 0:
                st.session_state.selected_outlet = outlet_list[0]

            col_left, col_right = st.columns([1.1, 1.2])

            with col_left:
                st.subheader("🗺️ Outlet Map & Navigation")
                map_center = [surveyor_lat if surveyor_lat else 26.8941, surveyor_lon if surveyor_lon else 80.9584]
                m = folium.Map(location=map_center, zoom_start=14)

                if surveyor_lat and surveyor_lon:
                    folium.Marker(
                        [surveyor_lat, surveyor_lon],
                        popup=f"Your Location ({selected_hunter})",
                        icon=folium.Icon(color="blue", icon="user", prefix="fa")
                    ).add_to(m)

                for idx, row in df_filtered_outlets.iterrows():
                    out_name = str(row.get(outlet_col, f"Outlet_{idx}"))
                    lat, lon = row['out_lat'], row['out_lon']

                    if pd.notna(lat) and pd.notna(lon):
                        is_selected = (out_name == st.session_state.selected_outlet)
                        is_done = out_name in st.session_state.surveys_completed

                        gmaps_url = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}"
                        dist_text = f"{row['distance_km']:.2f} km away" if 'distance_km' in row and row['distance_km'] < 9000 else ""
                        
                        popup_html = f"""
                        <div style="font-family: sans-serif; min-width: 150px;">
                            <b>{out_name}</b><br>
                            <small>{dist_text}</small><br>
                            Status: <b style="color:{'green' if is_done else 'red'};">{'Completed' if is_done else 'Pending'}</b><br><br>
                            <a href="{gmaps_url}" target="_blank" style="background-color: #2563eb; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; display: inline-block;">📍 Open in Google Maps</a>
                        </div>
                        """

                        if is_selected:
                            folium.Marker(
                                [lat, lon],
                                popup=folium.Popup(popup_html, max_width=250),
                                tooltip=out_name,
                                icon=folium.Icon(color="red", icon="star")
                            ).add_to(m)
                        else:
                            color = "green" if is_done else "orange"
                            folium.CircleMarker(
                                location=[lat, lon],
                                radius=8,
                                popup=folium.Popup(popup_html, max_width=250),
                                tooltip=out_name,
                                color=color,
                                fill=True,
                                fill_color=color,
                                fill_opacity=0.8
                            ).add_to(m)

                map_data = st_folium(m, width=550, height=480, key="survey_map")

                if map_data and map_data.get("last_object_clicked_tooltip"):
                    clicked_name = str(map_data["last_object_clicked_tooltip"]).strip()
                    if clicked_name in outlet_list and clicked_name != st.session_state.selected_outlet:
                        st.session_state.selected_outlet = clicked_name
                        st.rerun()

            with col_right:
                st.subheader(f"📝 Survey Form ({selected_hunter})")
                
                def on_outlet_change():
                    st.session_state.selected_outlet = st.session_state.outlet_select_key

                idx_selected = outlet_list.index(st.session_state.selected_outlet) if st.session_state.selected_outlet in outlet_list else 0

                selected_outlet = st.selectbox(
                    "Select Target Outlet", 
                    options=outlet_list,
                    index=idx_selected,
                    key="outlet_select_key",
                    on_change=on_outlet_change
                )

                out_data = df_filtered_outlets[df_filtered_outlets[outlet_col].astype(str) == st.session_state.selected_outlet].iloc[0]

                with st.form("dynamic_survey_form", clear_on_submit=False):
                    form_values = {}

                    channel_hierarchy = {}
                    if "Channel Sub Channel" in sheet_names:
                        csc_df = pd.read_excel(excel_file, sheet_name="Channel Sub Channel")
                        csc_df.columns = csc_df.columns.str.strip()
                        if "Channel Name" in csc_df.columns and "Sub Channel Name" in csc_df.columns:
                            for c_val, group in csc_df.groupby("Channel Name"):
                                channel_hierarchy[str(c_val).strip()] = group["Sub Channel Name"].dropna().astype(str).str.strip().tolist()

                    products_list = master_dropdowns.get("Products", master_dropdowns.get("Product ", []))

                    for col_heading in df_he_columns:
                        head_clean = col_heading.strip()
                        head_lower = head_clean.lower()

                        if head_lower in ["id"]:
                            form_values[head_clean] = f"SURVEY_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                        elif head_lower in ["date"]:
                            form_values[head_clean] = datetime.now().strftime("%Y-%m-%d")
                        elif head_lower in ["time"]:
                            form_values[head_clean] = datetime.now().strftime("%H:%M:%S")
                        elif head_lower in ["location"]:
                            form_values[head_clean] = f"{surveyor_lat},{surveyor_lon}" if surveyor_lat else "GPS Not Locked"

                        elif head_clean in df_filtered_outlets.columns or head_clean.upper() in [c.upper() for c in df_filtered_outlets.columns]:
                            matched_col = next((c for c in df_filtered_outlets.columns if c.upper() == head_clean.upper()), None)
                            val = str(out_data.get(matched_col, "")) if matched_col else ""
                            form_values[head_clean] = st.text_input(f"{head_clean} (Auto-filled)", value=val)

                        elif "outlet name" in head_lower:
                            form_values[head_clean] = st.text_input(head_clean, value=st.session_state.selected_outlet)

                        elif head_lower == "channel name":
                            c_options = list(channel_hierarchy.keys()) if channel_hierarchy else master_dropdowns.get("Channel Name", ["General"])
                            form_values[head_clean] = st.selectbox(head_clean, options=c_options, key="dyn_chan")

                        elif head_lower == "sub channel name":
                            sel_chan = st.session_state.get("dyn_chan", None)
                            sub_opts = channel_hierarchy.get(sel_chan, []) if sel_chan else master_dropdowns.get("Sub Channel Name", ["General"])
                            if not sub_opts:
                                sub_opts = master_dropdowns.get("Sub Channel Name", ["General"])
                            form_values[head_clean] = st.selectbox(head_clean, options=sub_opts)

                        elif "order" in head_lower or "product" in head_lower:
                            if products_list:
                                form_values[head_clean] = st.selectbox(head_clean, options=["None"] + products_list)
                            else:
                                form_values[head_clean] = st.text_input(head_clean)

                        elif "quantity" in head_lower:
                            form_values[head_clean] = st.number_input(head_clean, min_value=0, step=1)

                        elif "amount" in head_lower:
                            form_values[head_clean] = st.number_input(head_clean, min_value=0.0, step=10.0)

                        elif "image" in head_lower or "photo" in head_lower or "shop image" in head_lower:
                            st.markdown("**📷 Shop Photo Capture**")
                            enable_cam = st.checkbox("Click here to Open Live Camera", key="cam_toggle")
                            if enable_cam:
                                form_values[head_clean] = st.camera_input("Take Live Photo")
                            else:
                                form_values[head_clean] = None

                        else:
                            dropdown_opts = None
                            for key, opt_list in master_dropdowns.items():
                                if key.lower().replace(" ", "").replace("_", "") in head_lower.replace(" ", "").replace("_", ""):
                                    dropdown_opts = opt_list
                                    break

                            if dropdown_opts:
                                form_values[head_clean] = st.selectbox(head_clean, options=dropdown_opts)
                            else:
                                form_values[head_clean] = st.text_input(head_clean)

                    submitted = st.form_submit_button("Submit Survey Response", use_container_width=True)

                    if submitted:
                        img_col = next((c for c in df_he_columns if "image" in c.lower() or "photo" in c.lower()), None)
                        if img_col and not form_values.get(img_col):
                            st.error("⚠️ Photo capture karne ke liye 'Open Live Camera' tick karein.")
                        else:
                            if img_col and form_values.get(img_col):
                                img_file = form_values[img_col]
                                img_filename = f"{st.session_state.selected_outlet}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                                img_path = os.path.join(IMAGE_FOLDER, img_filename)
                                image = Image.open(img_file)
                                image.save(img_path)
                                form_values[img_col] = img_filename

                            save_survey_data(form_values)
                            st.session_state.surveys_completed.add(st.session_state.selected_outlet)
                            st.success(f"✅ '{st.session_state.selected_outlet}' ka survey submit ho gaya!")
                            st.rerun()

        # =====================================================================
        # MODE 2: ADMIN LIVE DASHBOARD (LAPTOP ONLY)
        # =====================================================================
        else:
            st.title("🖥️ Live Field Survey Admin Dashboard")

            total_outlets = len(df_outlets)
            current_completed = len(st.session_state.surveys_completed)
            current_pending = total_outlets - current_completed
            completion_rate = (current_completed / total_outlets * 100) if total_outlets > 0 else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("📍 Total Outlets", f"{total_outlets}")
            m2.metric("✅ Completed Surveys", f"{current_completed}", delta=f"{completion_rate:.1f}% Done")
            m3.metric("⏳ Pending Outlets", f"{current_pending}")
            m4.metric("👥 Active Surveyors", f"{len(hunter_list)}")

            st.markdown("---")

            st.subheader("🗺️ Live Map Tracking & Selective Filter")
            
            c_filter1, c_filter2 = st.columns(2)
            with c_filter1:
                selected_admin_hunter = st.selectbox(
                    "👤 Filter by Surveyor", 
                    options=["All Surveyors"] + hunter_list
                )
            with c_filter2:
                map_status_filter = st.selectbox(
                    "📌 Filter Outlets Status on Map", 
                    options=["All Points", "✅ Only Completed Points", "⏳ Only Pending Points", "📍 Show Only Surveyor's Live Location"]
                )

            if selected_admin_hunter != "All Surveyors":
                adm_outlets = df_outlets[df_outlets[hunter_col].astype(str) == selected_admin_hunter]
            else:
                adm_outlets = df_outlets

            adm_map = folium.Map(location=[26.8941, 80.9584], zoom_start=13)

            if surveyor_lat and surveyor_lon:
                folium.Marker(
                    [surveyor_lat, surveyor_lon],
                    popup=f"<b>📍 Active Surveyor Current GPS Location</b>",
                    tooltip="Surveyor Live Position",
                    icon=folium.Icon(color="blue", icon="user", prefix="fa")
                ).add_to(adm_map)

            if map_status_filter != "📍 Show Only Surveyor's Live Location":
                for idx, row in adm_outlets.iterrows():
                    out_name = str(row.get(outlet_col, f"Outlet_{idx}"))
                    h_owner = str(row.get(hunter_col, "Unknown"))
                    lat, lon = row['out_lat'], row['out_lon']

                    if pd.notna(lat) and pd.notna(lon):
                        is_done = out_name in st.session_state.surveys_completed
                        
                        if map_status_filter == "✅ Only Completed Points" and not is_done:
                            continue
                        if map_status_filter == "⏳ Only Pending Points" and is_done:
                            continue

                        color = "green" if is_done else "orange"
                        status_lbl = "Completed ✅" if is_done else "Pending ⏳"

                        folium.CircleMarker(
                            location=[lat, lon],
                            radius=7,
                            popup=f"<b>{out_name}</b><br>Hunter: {h_owner}<br>Status: <b>{status_lbl}</b>",
                            tooltip=f"{out_name} ({status_lbl})",
                            color=color,
                            fill=True,
                            fill_color=color,
                            fill_opacity=0.85
                        ).add_to(adm_map)

            st_folium(adm_map, width=1200, height=500, key="admin_master_map")

            st.markdown("---")

            st.subheader("📊 Surveyor-wise Live Progress Table")
            
            resp_df = load_survey_data()
            progress_data = []

            for h_name in hunter_list:
                h_outlets = df_outlets[df_outlets[hunter_col].astype(str) == h_name]
                h_total = len(h_outlets)
                
                h_outlet_names = set(h_outlets[outlet_col].dropna().astype(str).tolist())
                h_done = len(h_outlet_names.intersection(st.session_state.surveys_completed))
                h_pending = h_total - h_done
                h_pct = (h_done / h_total * 100) if h_total > 0 else 0

                progress_data.append({
                    "Surveyor / Hunter": h_name,
                    "Total Assigned": h_total,
                    "Completed Points ✅": h_done,
                    "Pending Points ⏳": h_pending,
                    "Completion %": f"{h_pct:.1f}%"
                })

            df_progress = pd.DataFrame(progress_data)
            st.dataframe(df_progress, use_container_width=True)

            st.subheader("📥 Download Live Field Responses")
            if not resp_df.empty:
                st.download_button(
                    "Download Complete Survey Responses (Excel)",
                    data=open(SURVEY_FILE, "rb").read() if os.path.exists(SURVEY_FILE) else b"",
                    file_name=f"Live_Survey_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.info("Abhi tak koi survey submit nahi hua hai.")

    except Exception as e:
        st.error(f"Error loading master file: {str(e)}")

else:
    st.info("👈 Server par `master_questions.xlsx` file rakhein.")