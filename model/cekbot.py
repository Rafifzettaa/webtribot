import csv
import requests
from datetime import datetime
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

# Inisialisasi logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_cek.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
# URL Indosat untuk cek NIK/KK
url_post = "https://myim3.indosatooredoo.com/ceknomor/checkForm"
url_get_result = "https://myim3.indosatooredoo.com/ceknomor/result"

# Fungsi untuk mengirim permintaan POST dan menangani redirect
def check_nik_kk(nik, kk):
    headers = {
        "Host": "myim3.indosatooredoo.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.140 Safari/537.36",
        "Origin": "https://myim3.indosatooredoo.com",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Referer": "https://myim3.indosatooredoo.com/ceknomor/",
    }

    payload = {
        "nik": nik,
        "kk": kk,
        "g-recaptcha-response": "",
        "send": "PERIKSA"
    }

    # Kirim POST request tanpa mengikuti redirect secara otomatis
    with requests.Session() as session:
        post_response = session.post(url_post, headers=headers, data=payload, allow_redirects=False)

        # Periksa apakah status code 302 (redirect)
        if post_response.status_code == 302:
            # Akses URL tujuan (result)
            get_response = session.get(url_get_result, headers=headers)

            if get_response.status_code == 200:
                # Parse HTML hasil
                soup = BeautifulSoup(get_response.text, "html.parser")
                nik_result = soup.find("h6")
                nomor_result = soup.find("ul", class_="list-unstyled margin-5-top")

                if nik_result and nomor_result:
                    # Mengambil nomor yang ditemukan
                    nomor_list = nomor_result.find_all("li")
                    nomor = [nomor.text.strip() for nomor in nomor_list]
                    
                    # Menghitung sisa berdasarkan jumlah nomor yang ditemukan
                    sisa = 3 - len(nomor)

                    return {
                        "status": True,
                        "nik": nik_result.text.strip(),
                        "nomor": nomor,
                        "sisa": sisa
                    }
                else:
                    return {
                        "status": False,
                        "message": "Data tidak ditemukan atau format respons berubah.",
                        "sisa": 3
                    }
            else:
                return {
                    "status": False,
                    "message": f"GET request failed with status code {get_response.status_code}",
                    "sisa": 3
                }
        else:
            return {
                "status": False,
                "message": f"POST request failed with status code {post_response.status_code}",
                "sisa": 3
            }


# Fungsi untuk memproses spreadsheet dari URL
async def process_spreadsheet_from_url(url):
    response = requests.get(url)
    response.raise_for_status()

    # Parsing CSV
    data = response.text.splitlines()
    reader = csv.reader(data)
    next(reader, None)  # Skip header

    results = [["NIK", "KK", "Status", "Nomor", "Message", "Sisa"]]

    for row in reader:
        nik, kk = row[0], row[1]
        result = check_nik_kk(nik, kk)  # Asumsikan check_nik_kk didefinisikan dengan benar

        if result["status"]:
            results.append([nik, kk, "Berhasil", ", ".join(result["nomor"]), "", result["sisa"]])
        else:
            results.append([nik, kk, "Gagal", "", result["message"], result["sisa"]])

    return results

# Fungsi untuk menyimpan hasil ke file
async def save_results(results, output_format):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    if output_format == "csv":
        filename = f"results_{timestamp}.csv"
        with open(filename, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerows(results)
    elif output_format == "txt":
        filename = f"results_{timestamp}.txt"
        with open(filename, "w") as file:
            for row in results:
                file.write(" | ".join(row) + "\n")
    elif output_format == "excel":
        import pandas as pd
        filename = f"results_{timestamp}.xlsx"
        df = pd.DataFrame(results, columns=["NIK", "KK", "Status", "Nomor", "Message", "Sisa"])
        df.to_excel(filename, index=False)

    return filename

# Fungsi untuk menangani perintah /url
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = " ".join(context.args).strip()

    if not user_input.startswith("https://"):
        await update.message.reply_text(
            "URL tidak valid. Harap gunakan format URL spreadsheet yang valid seperti:\n\n"
            "https://docs.google.com/spreadsheets/d/ID_SPREADSHEET/export?format=csv&gid=ID_SHEET\n\n"
            "Gantilah `ID_SPREADSHEET` dengan ID spreadsheet Anda dan `ID_SHEET` dengan ID sheet yang ingin diproses.\n\n"
            "Contoh: `/url https://docs.google.com/spreadsheets/d/1Rbyn4y9xyBnUAyR1bDid6QMmGqx1ltOY02fBS6mfJGI/export?format=csv&gid=1462660250`"
        )
        return
    context.user_data['spreadsheet_url'] = user_input

    # Kirimkan pilihan format output menggunakan tombol
    keyboard = [
        [InlineKeyboardButton("CSV", callback_data="csv"),
         InlineKeyboardButton("TXT", callback_data="txt"),
         InlineKeyboardButton("Excel", callback_data="excel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "URL diterima. Pilih format output:",
        reply_markup=reply_markup
    )

# Fungsi untuk menangani pilihan format output
async def handle_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    output_format = query.data
    spreadsheet_url = context.user_data.get('spreadsheet_url')

    if not spreadsheet_url:
        await query.edit_message_text("URL spreadsheet tidak ditemukan. Silakan ulangi proses.")
        return

    try:
        await query.edit_message_text("Sedang memproses... Mohon tunggu.")

        results = await process_spreadsheet_from_url(spreadsheet_url)
        filename = await save_results(results, output_format)

        with open(filename, "rb") as file:
            await query.message.reply_document(file, filename=filename)

        await query.message.reply_text("Proses selesai. File telah dikirimkan.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await query.message.reply_text(f"Terjadi kesalahan: {e}")

# Fungsi untuk memulai bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Untuk memulai, kirimkan URL spreadsheet dengan format berikut:\n\n"
        "https://docs.google.com/spreadsheets/d/ID_SPREADSHEET/export?format=csv&gid=ID_SHEET\n\n"
        "Gantilah `ID_SPREADSHEET` dengan ID spreadsheet Anda dan `ID_SHEET` dengan ID sheet yang ingin diproses.\n\n"
        "Contoh: `/url https://docs.google.com/spreadsheets/d/1Rbyn4y9xyBnUAyR1bDid6QMmGqx1ltOY02fBS6mfJGI/export?format=csv&gid=1462660250`\n\n"
        "Atau gunakan perintah `/url [link]` untuk memulai."
    )

# Fungsi utama untuk menjalankan bot
def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("TOKEN bot tidak ditemukan di environment variables.")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("url", handle_url))
    application.add_handler(CallbackQueryHandler(handle_format_choice))

    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
