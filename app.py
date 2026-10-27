"""Streamlit chat interface for the DCU Placement Preparation Agent (work in progress)."""
import streamlit as st

st.set_page_config(page_title="DCU Placement Preparation Agent")
st.title("DCU Placement Preparation Agent")
st.write("Upload your CV and paste a job description to start a practice session.")

cv_file = st.file_uploader("CV (PDF or Word)", type=["pdf", "docx"])
job_description = st.text_area("Target job description")

if st.button("Start session", disabled=not (cv_file and job_description)):
    st.info("Coordinator not connected yet.")  # TODO: call src.coordinator
