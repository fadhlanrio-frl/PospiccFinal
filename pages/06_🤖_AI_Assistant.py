import streamlit as st

import ai_assistant

st.set_page_config(page_title="AI Assistant - Pospicc", page_icon="🤖", layout="wide")
st.title("🤖 AI Assistant")
st.caption("Tanya dalam bahasa natural. Jawaban akan mengutip metrik dan status kesegaran data yang relevan.")

st.info(
    "⚠️ **Decision boundary:** Asisten ini tidak bisa dan tidak akan mengubah stock, membuat order, "
    "mengaktifkan iklan, mengubah budget, atau melakukan pembayaran. Hanya memberi rekomendasi berbasis data.",
    icon="⚠️",
)

SAMPLE_QUESTIONS = [
    "Produk mana yang perlu direstock bulan ini, dan kenapa?",
    "Biaya Shopee apa yang paling besar makan margin kita?",
    "Provinsi mana yang paling potensial untuk digarap lebih agresif?",
    "Produk mana yang return rate-nya tinggi dan kenapa?",
    "Berapa biaya voucher yang kita tanggung sendiri bulan ini?",
]

cols = st.columns(len(SAMPLE_QUESTIONS))
clicked_question = None
for col, q in zip(cols, SAMPLE_QUESTIONS):
    if col.button(q, use_container_width=True):
        clicked_question = q

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

question = st.chat_input("Tanyakan sesuatu tentang bisnis Pospicc...") or clicked_question

for role, text in st.session_state.chat_history:
    with st.chat_message(role):
        st.markdown(text)

if question:
    st.session_state.chat_history.append(("user", question))
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Menganalisis data dashboard..."):
            answer = ai_assistant.ask(question)
        st.markdown(answer)
    st.session_state.chat_history.append(("assistant", answer))
