import csv
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import os
import logging
from dotenv import load_dotenv

# Memuat file .env
load_dotenv()

# Inisialisasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_activity.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# URL endpoint untuk cek status kartu
url = "https://tri.co.id/api/v1/information/sim-status"

# Fungsi untuk cek status kartu dan aktivasi
def check_sim_status(msisdn):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.140 Safari/537.36",
        "Origin": "https://tri.co.id",
        "Referer": "https://tri.co.id/",
    }

    payload = {
        "action": "MSISDN_STATUS_WEB",
        "input1": "",
        "input2": "",
        "language": "ID",
        "msisdn": msisdn
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during request: {e}")
        return {
            "status": False,
            "message": f"Request Error: {e}"
        }

    if response.status_code == 200:
        data = response.json()
        if data.get("status"):
            iccid = data["data"].get("iccid", "")
            last_4_iccid = iccid[-4:] if iccid else "Tidak diketahui"
            return {
                "status": True,
                "card_status": data["data"].get("cardStatus", "Tidak diketahui"),
                "activation_status": data["data"].get("activationStatus", "Tidak diketahui"),
                "last_4_iccid": last_4_iccid,
            }
        else:
            return {
                "status": False,
                "message": data.get("message", "Tidak diketahui")
            }
    else:
        return {
            "status": False,
            "message": f"HTTP Error {response.status_code}"
        }

# Fungsi untuk membaca input dari textarea dan menyimpan ke CSV
def read_from_textarea_csv(text_data):
    results = [["MSISDN", "Card Status", "Activation Status", "Last 4 ICCID", "Message"]]

    msisdns = text_data.strip().split("\n")
    for msisdn in msisdns:
        msisdn = msisdn.strip()
        if msisdn.startswith("08"):
            msisdn = "628" + msisdn[2:]

        logger.info(f"Processing MSISDN: {msisdn}")
        result = check_sim_status(msisdn)

        if result["status"]:
            results.append([msisdn, result["card_status"], result["activation_status"], result["last_4_iccid"], ""])
        else:
            results.append([msisdn, "", "", "", result["message"]])

    # Simpan hasil ke file CSV
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename_csv = f"processed_{timestamp}.csv"
    with open(output_filename_csv, "w", newline="") as output_file:
        writer = csv.writer(output_file)
        writer.writerows(results)

    logger.info(f"Processing completed. Output saved to {output_filename_csv}")
    return output_filename_csv

# Fungsi untuk membaca input dari textarea dan menyimpan ke TXT
def read_from_textarea_txt(text_data):
    results = []
    msisdns = text_data.strip().split("\n")
    for msisdn in msisdns:
        msisdn = msisdn.strip()
        if msisdn.startswith("08"):
            msisdn = "628" + msisdn[2:]

        logger.info(f"Processing MSISDN: {msisdn}")
        result = check_sim_status(msisdn)

        if result["status"]:
            results.append(f"MSISDN: {msisdn} | Card Status: {result['card_status']} | Activation Status: {result['activation_status']} | Last 4 ICCID: {result['last_4_iccid']}\n")
        else:
            results.append(f"MSISDN: {msisdn} | Message: {result['message']}\n")

    # Simpan hasil ke file TXT
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename_txt = f"processed_{timestamp}.txt"
    with open(output_filename_txt, "w") as output_file:
        output_file.writelines(results)

    logger.info(f"Processing completed. Output saved to {output_filename_txt}")
    return output_filename_txt

# Fungsi untuk membaca input dari textarea dan menyimpan ke Excel
def read_from_textarea_excel(text_data):
    import pandas as pd
    results = []

    msisdns = text_data.strip().split("\n")
    for msisdn in msisdns:
        msisdn = msisdn.strip()
        if msisdn.startswith("08"):
            msisdn = "628" + msisdn[2:]

        logger.info(f"Processing MSISDN: {msisdn}")
        result = check_sim_status(msisdn)

        if result["status"]:
            results.append([msisdn, result["card_status"], result["activation_status"], result["last_4_iccid"], ""])
        else:
            results.append([msisdn, "", "", "", result["message"]])

    # Simpan hasil ke file Excel
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename_excel = f"processed_{timestamp}.xlsx"
    df = pd.DataFrame(results, columns=["MSISDN", "Card Status", "Activation Status", "Last 4 ICCID", "Message"])
    df.to_excel(output_filename_excel, index=False)

    logger.info(f"Processing completed. Output saved to {output_filename_excel}")
    return output_filename_excel

# Handler untuk perintah /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"User {update.effective_user.id} started the bot.")
    await update.message.reply_text(
        "Halo! Kirimkan MSISDN (pisahkan dengan enter) atau unggah file CSV untuk diproses."
    )

# Handler untuk input MSISDN dari pengguna
async def handle_textarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_data = update.message.text.strip()

    if not text_data:
        await update.message.reply_text("Silakan kirimkan MSISDN yang ingin diproses (pisahkan dengan enter).")
        return

    try:
        logger.info(f"User {update.effective_user.id} input MSISDN data via textarea.")
        
        # Kirimkan pilihan format output menggunakan inline keyboard
        keyboard = [
            [InlineKeyboardButton("CSV", callback_data="csv"),
             InlineKeyboardButton("TXT", callback_data="txt"),
             InlineKeyboardButton("Excel", callback_data="excel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Pilih format output yang diinginkan:",
            reply_markup=reply_markup
        )

        # Simpan data yang dikirim pengguna untuk pemrosesan selanjutnya
        context.user_data['text_data'] = text_data
    except Exception as e:
        logger.error(f"Error during textarea processing: {e}")
        await update.message.reply_text(f"Terjadi kesalahan: {e}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # Pastikan kita menunggu eksekusi dari query.answer()

    # Hapus tombol setelah pilihan dibuat
    await query.edit_message_reply_markup(reply_markup=None)  # Menghapus inline keyboard

    # Ambil data yang sudah disimpan oleh bot
    text_data = context.user_data.get('text_data', '')

    if not text_data:
        await query.message.reply_text("Data MSISDN tidak ditemukan.")
        return

    choice = query.data
    try:
        # Tampilkan konfirmasi bahwa pilihan sudah diterima
        await query.message.reply_text(f"Anda memilih format output: {choice.upper()}.\nSedang memproses...")

        # Proses sesuai dengan pilihan format
        if choice == "csv":
            output_filename = read_from_textarea_csv(text_data)
        elif choice == "txt":
            output_filename = read_from_textarea_txt(text_data)
        elif choice == "excel":
            output_filename = read_from_textarea_excel(text_data)

        # Kirimkan file hasil kepada pengguna
        with open(output_filename, "rb") as output_file:
            await query.message.reply_document(output_file, filename=output_filename)

        await query.message.reply_text("Proses selesai! File hasil telah dikirimkan.")
    except Exception as e:
        logger.error(f"Error during output processing: {e}")
        await query.message.reply_text(f"Terjadi kesalahan: {e}")


# Fungsi utama untuk menjalankan bot
def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("TOKEN bot tidak ditemukan di environment variables.")
    
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_textarea))  # Menangani input MSISDN
    application.add_handler(CallbackQueryHandler(button))  # Menangani pilihan output format

    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
