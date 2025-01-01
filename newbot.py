import os
import csv
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import pandas as pd

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("log/bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# URLs for NIK/KK checking
NIK_URL_POST = "https://myim3.indosatooredoo.com/ceknomor/checkForm"
NIK_URL_RESULT = "https://myim3.indosatooredoo.com/ceknomor/result"

# URL for SIM status checking
SIM_STATUS_URL = "https://tri.co.id/api/v1/information/sim-status"

# Function to check NIK/KK
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

    with requests.Session() as session:
        post_response = session.post(NIK_URL_POST, headers=headers, data=payload, allow_redirects=False)

        if post_response.status_code == 302:
            get_response = session.get(NIK_URL_RESULT, headers=headers)

            if get_response.status_code == 200:
                soup = BeautifulSoup(get_response.text, "html.parser")
                nik_result = soup.find("h6")
                nomor_result = soup.find("ul", class_="list-unstyled margin-5-top")

                if nik_result and nomor_result:
                    nomor_list = nomor_result.find_all("li")
                    nomor = [nomor.text.strip() for nomor in nomor_list]
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

# Function to check SIM status
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
        response = requests.post(SIM_STATUS_URL, headers=headers, json=payload, timeout=10)
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

# Command handler for /ceknik
async def cek_nik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received /ceknik with args: {context.args}")
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Format salah. Gunakan: /ceknik <NIK> <KK>")
        return

    nik, kk = args[0], args[1]
    result = check_nik_kk(nik, kk)
    if result["status"]:
        nomor_list = "\n".join(result["nomor"])
        await update.message.reply_text(
            f"NIK: {nik}\nNomor: {nomor_list}\nSisa: {result['sisa']}"
        )
    else:
        await update.message.reply_text(f"Gagal: {result['message']}")

async def ceknik_process_spreadsheet_from_url(url):
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
async def ceknik_save_results(results, output_format):
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

# Function to handle URL input and format choice
async def ceknik_handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# Function to handle format choice
async def ceknik_handle_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    output_format = query.data
    spreadsheet_url = context.user_data.get('spreadsheet_url')

    if not spreadsheet_url:
        await query.edit_message_text("URL spreadsheet tidak ditemukan. Silakan ulangi proses.")
        return

    try:
        await query.edit_message_text("Sedang memproses... Mohon tunggu.")

        # Fetch and process the spreadsheet data
        results = await ceknik_process_spreadsheet_from_url(spreadsheet_url)
        filename = await ceknik_save_results(results, output_format)

        with open(filename, "rb") as file:
            await query.message.reply_document(file, filename=filename)

        await query.message.reply_text("Proses selesai. File telah dikirimkan.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await query.message.reply_text(f"Terjadi kesalahan: {e}")
# Command handler for /nomor
async def nomor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ambil argumen yang dikirimkan bersama perintah /nomor
    args = context.args
    logger.info(f"nomor yang diterima: {args}")

    # Pastikan ada minimal dua nomor
    if len(args) < 2:
        await update.message.reply_text("Format salah. Harap masukkan minimal dua nomor. Gunakan: /nomor <Nomor1> <Nomor2> [Nomor3] ...")
        return

    # Proses setiap nomor yang diterima
    results = []
    for nomor in args:
        msisdn = nomor.strip()  # Pastikan ada spasi yang tidak perlu dibuang

        # Cek jika nomor diawali dengan "08", ubah menjadi format internasional
        if msisdn.startswith("08"):
            msisdn = "628" + msisdn[2:]

        logger.info(f"Processing MSISDN: {msisdn}")
        
        # Asumsi Anda sudah memiliki fungsi check_sim_status untuk memeriksa status kartu
        result = check_sim_status(msisdn)

        # Menyusun hasil untuk setiap nomor
        if result["status"]:
            results.append(f"Nomor: {msisdn}\nStatus Kartu: {result['card_status']}\nStatus Aktivasi: {result['activation_status']}\nICCID Terakhir: {result['last_4_iccid']}\n")
        else:
            results.append(f"Nomor: {msisdn}\nGagal diproses: {result['message']}\n")

    # Jika ada hasil, kirimkan pilihan format output
    if results:
        context.user_data['results'] = results  # Simpan hasil untuk diproses lebih lanjut
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
    else:
        await update.message.reply_text("Tidak ada hasil yang ditemukan.")
async def handle_msisdn_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mengecek apakah bot sedang menunggu MSISDN
    if context.user_data.get('waiting_for_msisdn', False):
        text_data = update.message.text.strip()
        logger.info(f"Text data received: {text_data}")
        
        if not text_data:
            await update.message.reply_text("Silakan kirimkan MSISDN yang ingin diproses (pisahkan dengan enter).")
            return
        
        try:
            logger.info(f"User {update.effective_user.id} input MSISDN data via /nomor command.")
            
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
            context.user_data['waiting_for_msisdn'] = False  # Reset after receiving MSISDN
        except Exception as e:
            logger.error(f"Error during MSISDN processing: {e}")
            await update.message.reply_text(f"Terjadi kesalahan: {e}")
    else:
        await update.message.reply_text("Perintah tidak dikenali. Gunakan /nomor untuk memulai pemrosesan MSISDN.")

async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    format_choice = query.data  # Format yang dipilih (csv, txt, excel)
    logger.info(f"User memilih format: {format_choice}")

    # Ambil hasil sebelumnya dari context
    results = context.user_data.get('results', [])
    if not results:
        await query.answer("Tidak ada data untuk diproses.")
        return

    # Persiapkan file berdasarkan format yang dipilih
    file_path = None
    if format_choice == "csv":
        # Membuat konten CSV
        file_content = "\n".join(results)
        file_path = "output.csv"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(file_content)
    elif format_choice == "txt":
        # Membuat konten TXT
        file_content = "\n".join(results)
        file_path = "output.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(file_content)
    elif format_choice == "excel":
        # Menggunakan pandas untuk membuat file Excel
        # Mengubah hasil menjadi dataframe pandas
        df = pd.DataFrame([r.split("\n") for r in results], columns=["Nomor", "Status Kartu", "Status Aktivasi", "ICCID Terakhir", "Pesan"])
        file_path = "output.xlsx"
        df.to_excel(file_path, index=False, engine='openpyxl')  # Simpan ke Excel menggunakan openpyxl

    # Kirimkan file yang telah dibuat
    if file_path:
        await query.answer(f"Format {format_choice.upper()} dipilih.")
        with open(file_path, "rb") as f:
            await query.message.reply_document(f)

        # Hapus file setelah dikirim untuk menjaga kebersihan
        os.remove(file_path)
        
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot aktif. Berikut adalah perintah yang dapat Anda gunakan:\n\n"
        "/ceknik <NIK> <KK> - Untuk memeriksa NIK dan KK\n"
        "/urlceknik <URL> - Untuk memeriksa data NIK/KK dari spreadsheet\n"
        "/nomor <MSISDN> - Untuk memeriksa status SIM. Kirimkan MSISDN untuk memeriksa status SIM."
    )

# Main function to run the bot
def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("Telegram bot token not found in environment variables.")

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ceknik", cek_nik))
    application.add_handler(CommandHandler("urlceknik", ceknik_handle_url))

    application.add_handler(CommandHandler("nomor", nomor))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msisdn_input))
    application.add_handler(CallbackQueryHandler(handle_format_selection))

    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()
