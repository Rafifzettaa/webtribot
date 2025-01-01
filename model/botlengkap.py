import os
import csv
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
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
        logging.FileHandler("bot.log"),
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

    # Kirim POST request tanpa mengikuti redirect secara otomatis
    with requests.Session() as session:
        post_response = session.post(NIK_URL_POST, headers=headers, data=payload, allow_redirects=False)

        # Periksa apakah status code 302 (redirect)
        if post_response.status_code == 302:
            # Akses URL tujuan (result)
            get_response = session.get(NIK_URL_RESULT, headers=headers)

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
# Fungsi untuk memproses spreadsheet dari URL
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

# Fungsi untuk menyimpan hasil ke file
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

# Fungsi untuk menangani perintah /url
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

        results = await process_spreadsheet_from_url(spreadsheet_url)
        filename = await save_results(results, output_format)

        with open(filename, "rb") as file:
            await query.message.reply_document(file, filename=filename)

        await query.message.reply_text("Proses selesai. File telah dikirimkan.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await query.message.reply_text(f"Terjadi kesalahan: {e}")

# Command handler for /cekstatus
async def cek_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

# Command handler for /urlceknik
async def url_cek_nik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or not args[0].startswith("https://"):
        await update.message.reply_text("URL tidak valid. Harap gunakan format URL yang valid.")
        return

    url = args[0]
    response = requests.get(url)
    response.raise_for_status()

    csv_data = response.text.splitlines()
    reader = csv.reader(csv_data)
    next(reader, None)

    results = []
    for row in reader:
        nik = row[0]
        kk = row[1]
        result = check_nik_kk(nik, kk)
        if result["status"]:
            results.append([nik, kk, ", ".join(result["nomor"]), result["sisa"]])
        else:
            results.append([nik, kk, "Gagal", result["message"]])

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = f"ceknik_{timestamp}.csv"
    with open(output_file, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["NIK", "KK", "Nomor", "Sisa"])
        writer.writerows(results)

    with open(output_file, "rb") as file:
        await update.message.reply_document(file, filename=output_file)

# Command handler for /urlcekstatus
async def url_cek_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args or not args[0].startswith("https://"):
        await update.message.reply_text("URL tidak valid. Harap gunakan format URL yang valid.")
        return

    url = args[0]
    response = requests.get(url)
    response.raise_for_status()

    csv_data = response.text.splitlines()
    reader = csv.reader(csv_data)
    next(reader, None)

    results = []
    for row in reader:
        msisdn = row[0]
        result = check_sim_status(msisdn)
        if result["status"]:
            results.append([msisdn, result["card_status"], result["activation_status"], result["last_4_iccid"]])
        else:
            results.append([msisdn, "Gagal", result["message"]])

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = f"cekstatus_{timestamp}.csv"
    with open(output_file, "w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["MSISDN", "Card Status", "Activation Status", "Last 4 ICCID"])
        writer.writerows(results)

    with open(output_file, "rb") as file:
        await update.message.reply_document(file, filename=output_file)
        
# Fungsi untuk membaca input dari textarea dan menyimpan ke CSV
def cekstatus_read_from_textarea_csv(text_data):
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
def cekstatus_read_from_textarea_txt(text_data):
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
def cekstatus_read_from_textarea_excel(text_data):
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
            output_filename = cekstatus_read_from_textarea_csv(text_data)
        elif choice == "txt":
            output_filename = cekstatus_read_from_textarea_txt(text_data)
        elif choice == "excel":
            output_filename = cekstatus_read_from_textarea_excel(text_data)

        # Kirimkan file hasil kepada pengguna
        with open(output_filename, "rb") as output_file:
            await query.message.reply_document(output_file, filename=output_filename)

        await query.message.reply_text("Proses selesai! File hasil telah dikirimkan.")
    except Exception as e:
        logger.error(f"Error during output processing: {e}")
        await query.message.reply_text(f"Terjadi kesalahan: {e}")


# Main function to run the bot
def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("Telegram bot token not found in environment variables.")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("ceknik", cek_nik))
    application.add_handler(CommandHandler("cekstatus", cek_status))
    application.add_handler(CommandHandler("urlceknik", url_cek_nik))
    application.add_handler(CommandHandler("urlcekstatus", url_cek_status))
    
    #perbarui fungsi ini untuk cekstatus Fungsi
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_textarea))  # Menangani input MSISDN
    application.add_handler(CallbackQueryHandler(button))  # Menangani pilihan output format

    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == "__main__":
    main()

