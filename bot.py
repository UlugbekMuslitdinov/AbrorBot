import os
from datetime import datetime
import telebot
from telebot.types import BotCommand, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
import sqlite3
import logging
import sys

# Ensure logs directory exists
log_file = "bot.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more detailed logs
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)  # Optional: Also print logs to console
    ]
)

# Log uncaught exceptions
def log_exceptions(exctype, value, traceback):
    logging.error("Uncaught exception", exc_info=(exctype, value, traceback))

sys.excepthook = log_exceptions


# Load environment variables
load_dotenv()

# Retrieve the token
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Ensure the token exists
if not TOKEN:
    raise ValueError("ERROR: TELEGRAM_BOT_TOKEN not found! Set it in the .env file.")

bot = telebot.TeleBot(TOKEN)

# Dictionary to keep track of which users are expected to provide data
user_states = {}
admin_selected_clients = {}  # To keep track of the client selected by the admin for adding an order
user_cart = {}  # To keep track of the products added to the cart by the admin
cur_product = {}

commands_list = [
    "/start", "/help", "/add_order", "/delete_order", "/edit_client", "/list_orders", "/list_products"
]


def create_db_connection():
    conn = sqlite3.connect('data.db')
    return conn


def create_db_tables():
    conn = create_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY AUTOINCREMENT , username TEXT, first_name TEXT, last_name TEXT, type TEXT DEFAULT client, saved_name TEXT, debt INTEGER DEFAULT 0, telegram_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products
                    (product_id INTEGER PRIMARY KEY, product_name TEXT, product_price INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS itemInOrder
                    (order_id INTEGER, product_id INTEGER, quantity INTEGER, price INTEGER, FOREIGN KEY(order_id) REFERENCES orders(order_id), FOREIGN KEY(product_id) REFERENCES products(product_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                    (order_id INTEGER PRIMARY KEY, user_id INTEGER, order_date TEXT, total_sum INTEGER, total_quantity INTEGER, total_debt INTEGER DEFAULT 0, before_order_debt INTEGER, is_confirmed INTEGER DEFAULT 0)''')
    conn.commit()


def redirect_to_command(message):
    if message.text == "/start":
        start(message)
    elif message.text == "/help":
        help(message)
    elif message.text == "/add_order":
        handle_add_order(message)
    elif message.text == "/delete_order":
        handle_delete_order(message)
    elif message.text == "/edit_client":
        handle_edit_client(message)
    elif message.text == "/list_orders":
        handle_list_orders(message)
    elif message.text == "/list_products":
        handle_list_products(message)
    else:
        bot.send_message(message.chat.id, "Noto`g`ri buyruq. Iltimos, quyidagi buyruqlardan birini tanlang:")
        bot.send_message(message.chat.id, "\n".join(commands_list))


# Wrapper to check if user exists for each command
def user_command_wrapper(func):
    def wrapper(message):
        user_id = str(message.from_user.id)
        if not user_exists(user_id):
            bot.send_message(message.chat.id,
                             "Sizning profilingiz topilmadi. Iltimos, foydalanishni boshlash uchun /start ni kiriting.")
        else:
            func(message)

    return wrapper


# Check if user is an admin
def is_admin(user_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user is not None and user[4] == 'admin'


# Check if user is a client
def is_client(user_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT type FROM users WHERE telegram_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    # Debug log
    print(f"Debug: User ID {user_id}, Query Result: {user}")
    return user is not None and user[0] == 'client'


# Function to list all clients for admin to select
def list_clients():
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE type='client'")
    clients = c.fetchall()
    conn.close()
    return {client[0]: {'first_name': client[2], 'last_name': client[3]} for client in clients}


def back_to_menu(message):
    user_id = str(message.from_user.id)
    if is_admin(user_id):
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton("Buyurtma qo'shish"), KeyboardButton("Buyurtmani o'chirish"))
        markup.add(KeyboardButton("Mijoz ma'lumotlarini o'zgartirish"), KeyboardButton("Mahsulotni tahrirlash"))
        markup.add(KeyboardButton("Buyurtmalarni ko'rish"))
        user_states[user_id] = None
        bot.send_message(message.chat.id, "Menyu", reply_markup=markup)
        print("Back to menu")
    else:
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton("Buyurtmalarni ko'rish"))  # View orders
        markup.add(KeyboardButton("To'lovni amalga oshirish"))  # New payment button
        user_states[user_id] = None
        bot.send_message(message.chat.id, "Menyu", reply_markup=markup)
        print("Back to menu")


def get_orders_number():
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    data = {row[0]: row for row in c.fetchall()}  # Convert rows to a dictionary if needed
    conn.close()
    num = 0
    for user_id, user_data in data.items():
        if user_data.get('type') == 'client':
            orders = user_data.get('orders', [])
            num += len(orders)
    return num


def get_max_order_id():
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    data = {row[0]: row for row in c.fetchall()}  # Convert rows to a dictionary if needed
    conn.close()
    max_id = 0
    for user_id, user_data in data.items():
        if user_data.get('type') == 'client':
            orders = user_data.get('orders', [])
            for order in orders:
                order_id = int(order['order_id'])
                if order_id > max_id:
                    max_id = order_id
    print("Max order ID:", max_id)
    return max_id



def create_payments_table():
    """
    Create the 'payments' table in the database if it doesn't exist.
    """
    conn = create_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            is_confirmed INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    conn.commit()
    conn.close()




# Admin selects a client to edit
@bot.message_handler(
    func=lambda message: message.text == "/edit_client" or message.text == "Mijoz ma'lumotlarini o'zgartirish")
@user_command_wrapper
def handle_edit_client(message):
    user_id = str(message.from_user.id)
    client_choice = message.text.strip()

    if client_choice == "Bosh menyu":
        back_to_menu(message)
        return

    if client_choice in commands_list:
        redirect_to_command(message)
        return

    if is_admin(user_id):
        clients = list_clients()

        if clients:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for client_id, client_data in clients.items():
                if client_data['last_name'] == '' or client_data['last_name'] is None:
                    markup.add(KeyboardButton(f"{client_data['first_name']} ({client_id})"))
                else:
                    markup.add(KeyboardButton(f"{client_data['first_name']} {client_data['last_name']} ({client_id})"))
            markup.add(KeyboardButton("Bosh menyu"))

            user_states[user_id] = 'selecting_client_for_edit'
            bot.send_message(message.chat.id, "O'zgartirish uchun mijozni tanlang:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Bunday mijoz topilmadi.")
    else:
        bot.send_message(message.chat.id, "Sizda mijozlarni o'zgartirishga ruxsat yo`q.")


def get_client_by_id(client_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (client_id,))
    client = c.fetchone()
    conn.close()
    return client

def get_client_discount(client_id):
    """
    Retrieve the last applied discount for a client from the database.
    """
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT discount FROM users WHERE user_id=?", (client_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result and result[0] is not None else 0


def create_db_connection():
    try:
        conn = sqlite3.connect('data.db')
        logging.info("Database connection established.")
        return conn
    except Exception as e:
        logging.error(f"Database connection error: {e}", exc_info=True)



# Handle the selection of a client for editing
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_client_for_edit')
@user_command_wrapper
def handle_select_client_for_edit(message):
    user_id = str(message.from_user.id)
    client_choice = message.text.strip()

    if client_choice == "Bosh menyu":
        back_to_menu(message)
        return

    if client_choice in commands_list:
        redirect_to_command(message)
        return

    # Extract client ID from the selected text (the ID is in parentheses)
    try:
        selected_client_id = client_choice.split('(')[-1].strip(')')
        print(f"Selected client ID: {selected_client_id}")
        admin_selected_clients[user_id] = selected_client_id
        print(f"Admin selected clients: {admin_selected_clients}")

        # Display the current client data
        client_data = get_client_by_id(selected_client_id)
        print(f"Client data: {client_data}")
        username = client_data[1] if client_data[1] else "None"
        first_name = client_data[2] if client_data[2] else "None"
        last_name = client_data[3] if client_data[3] else "None"
        saved_name = client_data[5] if client_data[5] else "None"
        debt = client_data[6] if client_data[6] else 0
        user_type = client_data[4] if client_data[4] else "None"
        discount_amount = get_client_discount(selected_client_id)
        client_info = (
            f"Mijoz haqida:\n"
            f"Username: {username}\n"
            f"Ism: {first_name}\n"
            f"Familiya: {last_name}\n"
            f"Sistemadagi Ism: {saved_name}\n"
            f"Qarzi: {debt:,} so'm\n"
            f"Type: {user_type.capitalize()}\n"
            f"So'nggi chegirma: {discount_amount:,.0f} so'm"
        )
        bot.send_message(message.chat.id, client_info)

        # Ask admin which field they want to edit
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton("Username"), KeyboardButton("Ism"), KeyboardButton("Familiya"))
        markup.add(KeyboardButton("Sistemadagi Ism"), KeyboardButton("Qarzi"), KeyboardButton("Type"))
        markup.add(KeyboardButton("Chegirma qo'shish"))  # New discount option
        markup.add(KeyboardButton("Mijozni o'chirish"))  # New option to delete the client
        markup.add(KeyboardButton("Bosh menyu"))
        user_states[user_id] = 'choosing_field_to_edit'
        bot.send_message(message.chat.id, "Qaysi maydonni o'zgartirish?", reply_markup=markup)

    except Exception as e:
        bot.send_message(message.chat.id, f"Noto`g'ri mijoz tanlandi: {e}")


# Handle field selection for editing
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'choosing_field_to_edit')
@user_command_wrapper
def handle_choose_field_to_edit(message):
    user_id = str(message.from_user.id)
    field_choice = message.text.strip()

    if field_choice == "Bosh menyu":
        back_to_menu(message)
        return

    if field_choice in commands_list:
        redirect_to_command(message)
        return

    if field_choice == "Mijozni o'chirish":
        # Confirm client deletion
        selected_client_id = admin_selected_clients.get(user_id)
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton("Ha"), KeyboardButton("Yo'q"))
        user_states[user_id] = 'confirming_client_deletion'
        bot.send_message(message.chat.id, f"Siz haqiqatan ham mijozni o'chirishni xohlaysizmi? ({selected_client_id})",
                         reply_markup=markup)
    elif field_choice in ["Username", "Ism", "Familiya", "Sistemadagi Ism", "Qarzi", "Type"]:
        # Special handling for 'Type' to show buttons
        if field_choice == "Type":
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Admin"), KeyboardButton("Client"))
            markup.add(KeyboardButton("Bosh menyu"))
            user_states[user_id] = 'editing_type'
            bot.send_message(message.chat.id, "Mijoz typeni tanlang:", reply_markup=markup)
        else:
            user_states[user_id] = f"editing_{field_choice.lower().replace(' ', '_')}"
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Bosh menyu"))
            bot.send_message(message.chat.id, f"Yangi {field_choice.lower()} kiriting:", reply_markup=markup)
    elif field_choice == "Chegirma qo'shish":
        user_states[user_id] = 'applying_discount'
        bot.send_message(message.chat.id, "Chegirma miqdorini kiriting:\n\n"
                                      "Masalan:\n"
                                      "- 5% (foiz sifatida)\n"
                                      "- 10000 (aniq miqdor sifatida)")
    else:
        bot.send_message(message.chat.id, "Invalid choice. Please select a valid field.")


@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'applying_discount')
@user_command_wrapper
def handle_apply_discount(message):
    user_id = str(message.from_user.id)
    discount_input = message.text.strip()
    selected_client_id = admin_selected_clients.get(user_id)

    if discount_input == "Bosh menyu":
        back_to_menu(message)
        return

    if discount_input in commands_list:
        redirect_to_command(message)
        return

    try:
        # Validate and parse discount input
        conn = create_db_connection()
        c = conn.cursor()

        # Fetch the current debt for the client
        c.execute("SELECT debt FROM users WHERE user_id=?", (selected_client_id,))
        result = c.fetchone()
        if not result:
            bot.send_message(message.chat.id, "Mijoz topilmadi.")
            return

        current_debt = result[0]
        discount_amount = 0

        if discount_input.endswith("%"):
            # Apply percentage discount
            percentage = float(discount_input.rstrip('%'))
            discount_amount = current_debt * (percentage / 100)
        else:
            # Apply fixed amount discount
            discount_amount = float(discount_input)

        # Ensure discount doesn't exceed the debt
        if discount_amount > current_debt:
            bot.send_message(message.chat.id, "Chegirma miqdori qarzdan ko'p bo'lishi mumkin emas.")
            return

        new_debt = current_debt - discount_amount

        # Update the debt in users table
        c.execute("UPDATE users SET debt=?, discount=? WHERE user_id=?", (new_debt, discount_amount, selected_client_id))

        # Update the total_debt in the latest order for the user
        c.execute("""
            UPDATE orders
            SET total_debt = ?
            WHERE user_id = ? AND order_id = (
                SELECT MAX(order_id) FROM orders WHERE user_id = ?
            )
        """, (new_debt, selected_client_id, selected_client_id))

        conn.commit()
        conn.close()

        # Notify admin
        bot.send_message(message.chat.id, 
                         f"Mijozga {discount_amount:,.0f} so'm chegirma qo'llandi.\n"
                         f"Yangi qarz miqdori: {new_debt:,.0f} so'm.")

        # Notify client
        client_telegram_id = get_user_telegram_id(selected_client_id)
        if client_telegram_id:
            bot.send_message(client_telegram_id, 
                             f"Sizga {discount_amount:,.0f} so'm chegirma qo'llandi.\n"
                             f"Hozirgi qarzingiz: {new_debt:,.0f} so'm.")

        # Reset state and show the edit client menu again
        user_states[user_id] = 'choosing_field_to_edit'
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton("Username"), KeyboardButton("Ism"), KeyboardButton("Familiya"))
        markup.add(KeyboardButton("Sistemadagi Ism"), KeyboardButton("Qarzi"), KeyboardButton("Type"))
        markup.add(KeyboardButton("Chegirma qo'shish"))
        markup.add(KeyboardButton("Mijozni o'chirish"))
        markup.add(KeyboardButton("Bosh menyu"))
        bot.send_message(message.chat.id, "Qaysi maydonni o'zgartirishni tanlang:", reply_markup=markup)
        
    except ValueError:
        bot.send_message(message.chat.id, "Chegirma miqdori noto'g'ri kiritilgan. Iltimos, qaytadan kiriting.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Xatolik yuz berdi: {e}")



def delete_user(user_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

# Handle client deletion confirmation
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'confirming_client_deletion')
@user_command_wrapper
def handle_confirm_client_deletion(message):
    user_id = str(message.from_user.id)
    confirmation = message.text.strip()

    if confirmation == "Ha":
        # Proceed to delete the client
        selected_client_id = admin_selected_clients.get(user_id)
        user = get_client_by_id(selected_client_id)
        if user:
            # Send a message to the deleted user
            try:
                bot.send_message(user[7],
                                 "Sizning profilingiz o'chirildi. Bottan foydalanish uchun /start ni kiriting.")
            except Exception as e:
                print(f"Could not send message to deleted user: {e}")

            # Delete the user from the database
            delete_user(user[0])
            bot.send_message(message.chat.id, f"Mijoz ({selected_client_id}) muvaffaqiyatli o'chirildi.")
        else:
            bot.send_message(message.chat.id, "Mijoz topilmadi.")

        # Reset state and return to menu
        user_states[user_id] = None
        admin_selected_clients[user_id] = None
        back_to_menu(message)
    elif confirmation == "Yo'q":
        bot.send_message(message.chat.id, "Mijoz o'chirilmaydi.")
        # Reset state and return to menu
        user_states[user_id] = None
        admin_selected_clients[user_id] = None
        back_to_menu(message)
    else:
        bot.send_message(message.chat.id, "Noto`g'ri tanlov. Iltimos, 'Ha' yoki 'Yo'q' ni tanlang.")


# Handle updating the selected field
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) 
                     and isinstance(user_states.get(str(message.from_user.id)), str) 
                     and user_states.get(str(message.from_user.id)).startswith('editing'))
def handle_edit_field(message):
    user_id = str(message.from_user.id)
    state = user_states.get(user_id)
    new_value = message.text.strip()

    if new_value == "Bosh menyu":
        back_to_menu(message)
        return

    if new_value in commands_list:
        redirect_to_command(message)
        return

    if state.startswith('editing_product_'):
        selected_product_id = cur_product.get(user_id)
        if not selected_product_id:
            bot.send_message(message.chat.id, "Mahsulot tanlanmadi. Iltimos, qayta urinib ko'ring.")
            return

        conn = create_db_connection()
        c = conn.cursor()

        if state == 'editing_product_name':
            c.execute("UPDATE products SET product_name=? WHERE product_id=?", (new_value, selected_product_id))
            conn.commit()
            bot.send_message(message.chat.id, f"Mahsulot nomi muvaffaqiyatli o'zgartirildi: {new_value}")
        elif state == 'editing_product_price':
            try:
                new_price = int(new_value)
                c.execute("UPDATE products SET product_price=? WHERE product_id=?", (new_price, selected_product_id))
                conn.commit()
                bot.send_message(message.chat.id, f"Mahsulot narxi muvaffaqiyatli o'zgartirildi: {new_price:,}")
            except ValueError:
                bot.send_message(message.chat.id, "Narx noto'g'ri formatda. Iltimos, raqam kiriting.")

        conn.close()
        user_states[user_id] = None
        cur_product[user_id] = None
        back_to_menu(message)

    elif state.startswith('editing_'):
        selected_client_id = admin_selected_clients.get(user_id)
        if not selected_client_id:
            bot.send_message(message.chat.id, "Mijoz tanlanmangan. Iltimos, qaytadan urinib ko`ring.")
            return

        conn = create_db_connection()
        c = conn.cursor()

        if state == 'editing_username':
            c.execute("UPDATE users SET username=? WHERE user_id=?", (new_value, selected_client_id))
            bot.send_message(message.chat.id, f"Username o`zgartirildi '{new_value}'.")
        elif state == 'editing_ism':
            c.execute("UPDATE users SET first_name=? WHERE user_id=?", (new_value, selected_client_id))
            bot.send_message(message.chat.id, f"Ism o`zgartirildi '{new_value}'.")
        elif state == 'editing_familiya':
            c.execute("UPDATE users SET last_name=? WHERE user_id=?", (new_value, selected_client_id))
            bot.send_message(message.chat.id, f"Familiya o`zgartirildi '{new_value}'.")
        elif state == 'editing_sistemadagi_ism':
            c.execute("UPDATE users SET saved_name=? WHERE user_id=?", (new_value, selected_client_id))
            bot.send_message(message.chat.id, f"Sistemadagi ism o`zgartirildi '{new_value}'.")
        elif state == 'editing_qarzi':
            try:
                new_value = int(new_value)
                c.execute("UPDATE users SET debt=?, discount=0 WHERE user_id=?", (new_value, selected_client_id))
                bot.send_message(message.chat.id, f"Qarz o`zgartirildi {new_value:,} so'm va chegirma 0 ga qayta tiklandi.")
                c.execute("SELECT telegram_id FROM users WHERE user_id=?", (selected_client_id,))
                client_telegram_id = c.fetchone()
                if client_telegram_id and client_telegram_id[0]:
                    bot.send_message(client_telegram_id[0], f"Sizning qarzingiz o'zgartirildi. Hozirgi qarzingiz: {new_value:,} so'm.")
            except ValueError:
                bot.send_message(message.chat.id, "Qarzni noto`g`ri kiritdingiz. Iltimos, qaytadan kiriting.")
        elif state == 'editing_type':
            if new_value in ['Admin', 'Client']:
                c.execute("UPDATE users SET type=? WHERE user_id=?", (new_value.lower(), selected_client_id))
                bot.send_message(message.chat.id, f"User type o`zgartirildi '{new_value.lower()}'.")
            else:
                bot.send_message(message.chat.id, "Typeni noto`g`ri kiritdingiz. Iltimos, qaytadan kiriting.")

        conn.commit()
        conn.close()

        user_states[user_id] = None
        admin_selected_clients[user_id] = None
        back_to_menu(message)

    else:
        bot.send_message(message.chat.id, "Amalni qayta aniqlab bo'lmadi. Iltimos, qayta urinib ko'ring.")


def user_exists(telegram_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    user = c.fetchone()
    conn.close()
    return user is not None


def create_user(telegram_id, username, first_name, last_name, user_type):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO users (telegram_id, username, first_name, last_name, type) VALUES (?, ?, ?, ?, ?)",
              (telegram_id, username, first_name, last_name, user_type))
    conn.commit()
    conn.close()


# Функция, которая выполняется при команде /start
@bot.message_handler(commands=['start'])
def start(message):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    data = {row[0]: row for row in c.fetchall()}  # Convert rows to a dictionary if needed
    conn.close()
    create_db_tables()
    create_payments_table()  # Add this line to create the 'payments' table
    user_id = str(message.from_user.id)

    if not user_exists(user_id):
        create_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name,
                    'client')
        bot.send_message(message.chat.id, f"Salom, {message.from_user.first_name}! Sizning ma`lumotlarinigiz saqlandi.")
    else:
        bot.send_message(message.chat.id, f"Qaytadan salom, {message.from_user.first_name}!")
    back_to_menu(message)


# Function to parse user input and create an order
def parse_order_input(message_text):
    lines = message_text.strip().split("\n")
    print(lines)

    # Extract saved name, debt, and order date from the first line
    first_line = lines[0].split("  ")
    saved_name = first_line[0]
    before_order_debt = int("".join(first_line[2].split()[:-1]))
    print(before_order_debt)

    debt = "".join(((lines[-2].split("  "))[-1]).split()[:-1])
    debt = int(debt)

    # Format the order date by replacing commas with slashes
    order_date = first_line[-1].replace(",", "/")

    # Skip header line "Наименование товара  Цена  Количество(кб)  Оплата  Перечисление  Остаток долга"
    product_lines = lines[2:-2]

    products = []

    for line in product_lines:
        parts = line.split("  ")
        if len(parts) < 3:
            continue  # Skip lines that don't have enough information

        product_name = parts[0]
        price_str = "".join(parts[1].split()[:-1])
        product_price = int(price_str) if price_str else 0

        product_quantity = int(parts[2]) if parts[2] != "" else 0

        if product_name != "" and product_price != "" and product_quantity != "":
            products.append({
                'product_name': product_name,
                'product_price': product_price,
                'product_quantity': product_quantity
            })

    # Extract the final summary line (Jami summa)
    summary_line = lines[-1].split("  ")
    second_last = lines[-2].split("  ")
    total_sum = "".join(second_last[1].split()[:-1])
    total_sum = int(total_sum)
    total_quantity = summary_line[2]
    total_quantity = int(total_quantity)
    total_debt = int("".join(summary_line[-1].split()[:-1]))

    return saved_name, debt, order_date, products, total_sum, total_quantity, total_debt, before_order_debt


# Function to add an order from parsed input
def add_order(user_id, saved_name, debt, order_date, products, total_sum, total_quantity, total_debt, before_order_debt):
    conn = create_db_connection()
    c = conn.cursor()
    
    # Add the new order to the database
    c.execute(
        "INSERT INTO orders (user_id, order_date, total_sum, total_quantity, total_debt, before_order_debt, is_confirmed) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, order_date, total_sum, total_quantity, total_debt, before_order_debt, 0)
    )
    order_id = c.lastrowid  # Get the ID of the newly inserted order

    # Add each product to the itemInOrder table
    for product in products:
        product_id = get_product_id_by_name(product['product_name'])
        c.execute(
            "SELECT product_name, product_price FROM products WHERE product_id = ?", (product_id,)
        )
        product_data = c.fetchone()
        if product_data:
            product_name, product_price = product_data
            c.execute(
                "INSERT INTO itemInOrder (order_id, product_id, product_name, product_price, quantity, price) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (order_id, product_id, product_name, product_price, product['product_quantity'], product['product_price'])
            )
    
    # Update the user's debt in the database
    c.execute("UPDATE users SET debt = ? WHERE user_id = ?", (total_debt, user_id))
    conn.commit()
    conn.close()

    print(f"Order added for user {user_id}: Order ID {order_id}")
    return order_id



def print_orders(orders):
    message = ""
    for order in orders:
        formatted_total_sum = "{:,}".format(order['total_sum']).replace(",", " ")
        message += f"Buyurtma ID: {order['order_id']}, miqdor: {formatted_total_sum:,}, sana: {order['order_date']} "
        if order['is_confirmed']:
            message += "Tasdiqlangan\n"
        else:
            message += "Tasdiqlanmagan\n"
        message += "\n"
    return message


# Function to list all orders for a user
def list_orders(user_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    data = {row[0]: row for row in c.fetchall()}  # Convert rows to a dictionary if needed
    conn.close()
    user_data = data.get(user_id, None)

    if is_admin(user_id):
        orders = {}
        for user_id, user_data in data.items():
            if user_data.get('type') == 'client':
                # Include the first name, last name, and debt for each client
                user_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
                debt = user_data.get('total_debt', 0)

                orders.update({f"{user_name} \nQarz: {'{:,}'.format(debt)} сум": user_data.get('orders', [])})
        if orders:
            message = ""
            for user_id, orders in orders.items():
                message += f"Mijoz: {user_id}\n"
                if orders:
                    for order in orders:

                        message += (f"Buyurtma ID: {order['order_id']}, miqdor: {'{:,}'.format(order['total_sum'])}, "
                                    f"sana: {order['order_date']}, ")
                        if order['is_confirmed']:
                            message += "Tasdiqlangan\n"
                        else:
                            message += "Tasdiqlanmagan\n"
                    message += "\n"
                else:
                    message += "Buyurtmalari topilmadi.\n\n"
            return message
        else:
            return "Buyurtmalar topilmadi."

    if user_data:
        orders = user_data.get('orders', [])
        if orders:
            message = ""
            for order in orders:
                formatted_total_sum = "{:,}".format(order['total_sum']).replace(",", " ")
                message += (f"Buyurtma ID: {order['order_id']}, Miqdor: {formatted_total_sum:,} so'm, "
                            f"Sana: {order['order_date']}\n")

                # Call list_products to include products for each order
                message += list_products(user_id, order['order_id']) + "\n\n"
            return message
        else:
            return "Buyurtma topilmadi."
    return "Mijoz topilmadi."   


def list_orders_db(telegram_id):
    conn = create_db_connection()
    c = conn.cursor()

    # Fetch user_id from the telegram_id
    c.execute("SELECT user_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user = c.fetchone()

    if not user:
        print(f"Debug: Telegram ID {telegram_id} not linked to any user.")
        return []  # Return an empty list if no user is found

    user_id = user[0]
    print(f"Debug: Matched Telegram ID {telegram_id} to User ID {user_id}")

    # Fetch orders for the user_id
    c.execute("SELECT * FROM orders WHERE user_id = ?", (user_id,))
    orders = c.fetchall()
    conn.close()
    print(f"Debug: Orders for User ID {user_id}: {orders}")
    return orders



def get_user_debt(user_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT debt FROM users WHERE user_id=?", (user_id,))
    debt = c.fetchone()
    conn.close()
    return debt[0] if debt else 0


def list_orders_db_admin():
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM orders")
    orders = c.fetchall()
    conn.close()
    return orders


def get_debt(user_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    data = {row[0]: row for row in c.fetchall()}  # Convert rows to a dictionary if needed
    conn.close()
    user_data = data.get(user_id, None)
    if user_data:
        return user_data.get('total_debt', 0)
    return 0


# Function to list all products in a specific order
def list_products(user_id, order_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM orders")
    orders = c.fetchall()
    conn.close()
    
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user_data = c.fetchone()
    conn.close()

    if user_data:
        orders = user_data.get('orders', [])
        for order in orders:
            if order['order_id'] == order_id:
                # Filter products with quantity greater than 0
                products = [product for product in order['products'] if product['product_quantity'] > 0]
                if products:
                    return "\n".join([
                        f"Mahsulot: {product['product_name']}, Narx: {'{:,}'.format(product['product_price']).replace(',', ' ')}, "
                        f"Miqdori: {product['product_quantity']:,}"
                        for product in products
                    ])
                else:
                    return "Mahsulot topilmadi."
        return "Buyurtma topilmadi."
    return "Mijoz topilmadi."


# Step 1: Handle the /add_order command or the "Buyurtma qo'shish" button
@bot.message_handler(func=lambda message: message.text == "Buyurtma qo'shish" or message.text == "/add_order")
def handle_add_order(message):
    user_id = str(message.from_user.id)

    if is_admin(user_id):
        clients = list_clients()

        if clients:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for client_id, client_data in clients.items():
                if client_data['last_name'] == '' or client_data['last_name'] is None:
                    markup.add(KeyboardButton(f"{client_data['first_name']} ({client_id})"))
                else:
                    markup.add(KeyboardButton(f"{client_data['first_name']} {client_data['last_name']} ({client_id})"))
            markup.add(KeyboardButton("Bosh menyu"))

            user_states[user_id] = 'selecting_client'
            bot.send_message(message.chat.id, "Mijozni tanlang:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Mijozlar topilmadi.")
    else:
        bot.send_message(message.chat.id, "Sizda buyurtma qo`shishga ruxsat yo`q.")


def products_list_keyboard():
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    conn.close()
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for product in products:
        markup.add(KeyboardButton(product[1]))

    markup.add(KeyboardButton("Mahsulot qo'shish"))
    markup.add(KeyboardButton("Buyurtma yig'ildi"))
    markup.add(KeyboardButton("Bosh menyu"))
    return markup

#--------------------------------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------------------------------
#-------------------------------------------------------------------------------------------------------------------------------------------- 
#--------------------------------------------------------------------------------------------------------------------------------------------

@bot.message_handler(func=lambda message: message.text == "Mahsulotni tahrirlash")
@user_command_wrapper
def handle_edit_product_menu(message):
    user_id = str(message.from_user.id)
    
    # Fetch products from the database
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT product_id, product_name, product_price FROM products")
    products = c.fetchall()
    conn.close()
    
    # Check if there are products to edit
    if not products:
        bot.send_message(message.chat.id, "Hech qanday mahsulot topilmadi.")
        back_to_menu(message)
        return

    # Display products to the admin
    markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    for product in products:
        product_text = f"{product[1]} - {product[2]:,} so'm (ID: {product[0]})"
        markup.add(KeyboardButton(product_text))
    markup.add(KeyboardButton("Bosh menyu"))
    
    user_states[user_id] = 'selecting_product'
    bot.send_message(message.chat.id, "Tahrir uchun mahsulotni tanlang:", reply_markup=markup)


@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_product')
@user_command_wrapper
def handle_product_selection(message):
    user_id = str(message.from_user.id)
    product_choice = message.text.strip()

    if product_choice == "Bosh menyu":
        back_to_menu(message)
        return

    try:
        # Extract product ID from the selected text
        product_id = int(product_choice.split("(ID: ")[-1].strip(")"))
        cur_product[user_id] = product_id

        # Display options for editing or deleting
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton("Nomi o'zgartirish"), KeyboardButton("Narxi o'zgartirish"))
        markup.add(KeyboardButton("Mahsulotni o'chirish"))
        markup.add(KeyboardButton("Bosh menyu"))
        user_states[user_id] = 'choosing_product_action'
        bot.send_message(message.chat.id, "Qanday amalni bajarmoqchisiz?", reply_markup=markup)
    except Exception as e:
        bot.send_message(message.chat.id, f"Noto'g'ri mahsulot tanlandi: {e}")


@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'choosing_product_action')
@user_command_wrapper
def handle_product_action(message):
    user_id = str(message.from_user.id)
    action_choice = message.text.strip()
    selected_product_id = cur_product.get(user_id)

    if action_choice == "Bosh menyu":
        back_to_menu(message)
        return

    if action_choice == "Nomi o'zgartirish":
        user_states[user_id] = 'editing_product_name'
        bot.send_message(message.chat.id, "Yangi nomni kiriting:")
    elif action_choice == "Narxi o'zgartirish":
        user_states[user_id] = 'editing_product_price'
        bot.send_message(message.chat.id, "Yangi narxni kiriting:")
    elif action_choice == "Mahsulotni o'chirish":
        if selected_product_id:
            delete_product(selected_product_id)
            bot.send_message(message.chat.id, f"Mahsulot (ID: {selected_product_id}) muvaffaqiyatli o'chirildi.")
            user_states[user_id] = None
            cur_product[user_id] = None
            back_to_menu(message)
        else:
            bot.send_message(message.chat.id, "Mahsulot tanlanmadi. Iltimos, qayta urinib ko'ring.")
    else:
        bot.send_message(message.chat.id, "Noto'g'ri tanlov. Iltimos, qayta urinib ko'ring.")


@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'editing_product_name')
@user_command_wrapper
def handle_edit_product_name(message):
    user_id = str(message.from_user.id)
    new_name = message.text.strip()
    selected_product_id = cur_product.get(user_id)  # Focus only on the product, not the client

    if selected_product_id:
        conn = create_db_connection()
        c = conn.cursor()
        c.execute("UPDATE products SET product_name=? WHERE product_id=?", (new_name, selected_product_id))
        conn.commit()
        conn.close()

        bot.send_message(message.chat.id, f"Mahsulot nomi muvaffaqiyatli o'zgartirildi: {new_name}")
        user_states[user_id] = None
        cur_product[user_id] = None
        back_to_menu(message)
    else:
        bot.send_message(message.chat.id, "Mahsulot tanlanmadi. Iltimos, qayta urinib ko'ring.")


@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'editing_product_price')
@user_command_wrapper
def handle_edit_product_price(message):
    user_id = str(message.from_user.id)
    new_price = message.text.strip()
    selected_product_id = cur_product.get(user_id)

    try:
        new_price = int(new_price)
        if selected_product_id:
            conn = create_db_connection()
            c = conn.cursor()
            c.execute("UPDATE products SET product_price=? WHERE product_id=?", (new_price, selected_product_id))
            conn.commit()
            conn.close()

            bot.send_message(message.chat.id, f"Mahsulot narxi muvaffaqiyatli o'zgartirildi: {new_price:,}")
            user_states[user_id] = None
            cur_product[user_id] = None
            back_to_menu(message)
        else:
            bot.send_message(message.chat.id, "Mahsulot tanlanmadi. Iltimos, qayta urinib ko'ring.")
    except ValueError:
        bot.send_message(message.chat.id, "Narx noto'g'ri formatda. Iltimos, raqam kiriting.")


def delete_product(product_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE product_id=?", (product_id,))
    conn.commit()
    conn.close()


#--------------------------------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------------------------------

# Step 2: Handle the selection of a client or creating a new client
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_client')
@user_command_wrapper
def handle_select_client(message):
    user_id = str(message.from_user.id)
    client_choice = message.text.strip()

    if client_choice == "Bosh menyu":
        back_to_menu(message)
        return

    if client_choice in commands_list:
        redirect_to_command(message)
        return

    # Extract client ID from the selected text (the ID is in parentheses)
    try:
        selected_client_id = client_choice.split('(')[-1].strip(')')
        admin_selected_clients[user_id] = selected_client_id
        user_states[user_id] = 'awaiting_order_data'
        user_cart[selected_client_id] = {}
        cur_product[selected_client_id] = None
        markup = products_list_keyboard()
        bot.send_message(message.chat.id, "Buyurtma maxsulotlarini tanlang:", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, "Noto`g`ri mijoz tanlandi. Iltimos, qaytadan urinib ko`ring.")


def get_product_id_by_name(product_name):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT product_id FROM products WHERE product_name=?", (product_name,))
    product_id = c.fetchone()
    conn.close()
    return product_id[0] if product_id else None


# Step 3: Handle the user's input data for orders
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'awaiting_order_data')
@user_command_wrapper
def receive_order_data(message):
    user_id = str(message.from_user.id)
    user_input = message.text.strip()
    selected_client_id = admin_selected_clients.get(user_id)

    keyboard = products_list_keyboard()

    if message.text == "Bosh menyu":
        back_to_menu(message)
        return

    if message.text in commands_list:
        redirect_to_command(message)
        return

    if message.text == "Mahsulot qo'shish":
        bot.send_message(message.chat.id, "Yangi mahsulot nomini va narxini ko'rsatilgan tartibda kiriting.")
        bot.send_message(message.chat.id, "Masalan: Pomidor, 5000")
        user_states[user_id] = 'adding_new_product'
        return

    if selected_client_id:
        if message.text == "Buyurtma yig'ildi":
            # confirm cart
            cart = user_cart[selected_client_id]
            mes, total_sum = confirm_cart(cart)
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Ha"), KeyboardButton("Yo'q"))
            bot.send_message(message.chat.id, mes, reply_markup=markup)
            user_states[user_id] = 'confirming_order'
        else:
            # add product to the cart and ask quantity
            product_id = get_product_id_by_name(user_input)
            user_cart[selected_client_id][product_id] = 0
            cur_product[selected_client_id] = product_id
            bot.send_message(message.chat.id, "Mahsulot miqdorini kiriting:")
            user_states[user_id] = 'awaiting_product_quantity'
    else:
        bot.send_message(message.chat.id, "Mijoz tanlanmagan. Iltimos, qaytadan urinib ko`ring.")


# Step 4: Handle the addition of a new product
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'adding_new_product')
@user_command_wrapper
def add_new_product(message):
    user_id = str(message.from_user.id)
    user_input = message.text.strip()

    if message.text == "Bosh menyu":
        back_to_menu(message)
        return

    if message.text in commands_list:
        redirect_to_command(message)
        return

    try:
        conn = create_db_connection()
        c = conn.cursor()
        product_name, product_price = user_input.split(", ")
        c.execute("INSERT INTO products (product_name, product_price) VALUES (?, ?)", (product_name.strip(), product_price))
        conn.commit()
        conn.close()
        keyboard = products_list_keyboard()
        bot.send_message(message.chat.id, "Yangi mahsulot muvaffaqiyatli qo`shildi.", reply_markup=keyboard)
        user_states[user_id] = 'awaiting_order_data'
    except ValueError:
        # Handle specific unpacking errors
        bot.send_message(
            message.chat.id, 
            "Mahsulotni qo`shishda xatolik yuz berdi: Yangi mahsulot nomini va narxini ko'rsatilgan tartibda kiriting. Masalan: Pomidor, 5000"
        )
    except Exception as e:
        # Handle other exceptions
        bot.send_message(message.chat.id, f"Mahsulotni qo`shishda xatolik yuz berdi: {e}")
        user_states[user_id] = None


def user_cart_to_str(cart):
    message = ""
    for product_id, quantity in cart.items():
        conn = create_db_connection()
        c = conn.cursor()
        c.execute("SELECT product_name FROM products WHERE product_id=?", (product_id,))
        product_name = c.fetchone()
        conn.close()
        message += f"{product_name[0]}: {quantity}\n"
    return message


# Step 5: Handle the user's input for product quantity
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'awaiting_product_quantity')
@user_command_wrapper
def receive_product_quantity(message):
    user_id = str(message.from_user.id)
    user_input = message.text.strip()
    selected_client_id = admin_selected_clients.get(user_id)

    if message.text == "Bosh menyu":
        back_to_menu(message)
        return

    if message.text in commands_list:
        redirect_to_command(message)
        return

    if selected_client_id:
        if user_input.isdigit():
            product_id = cur_product[selected_client_id]
            user_cart[selected_client_id][product_id] = int(user_input)
            bot.send_message(message.chat.id, "Mahsulot qo'shildi.")
            bot.send_message(message.chat.id, user_cart_to_str(user_cart[selected_client_id]))
            print(user_cart)
            user_states[user_id] = 'awaiting_order_data'
            markup = products_list_keyboard()  # Display the product selection menu again
            bot.send_message(message.chat.id, "Iltimos, mahsulotni tanlang yoki menyudan birini tanlang:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Miqdor raqam bo'lishi kerak.")
    else:
        bot.send_message(message.chat.id, "Mijoz tanlanmagan. Iltimos, qaytadan urinib ko`ring.")


def confirm_cart(cart):
    message = "Sizning buyurtmangiz:\n"
    total_sum = 0
    for product_id, quantity in cart.items():
        conn = create_db_connection()
        c = conn.cursor()
        c.execute("SELECT product_name, product_price FROM products WHERE product_id=?", (product_id,))
        product = c.fetchone()
        conn.close()
        product_name = product[0]
        product_price = product[1]
        total_sum += product_price * quantity
        message += f"{product_name}: {quantity} x {product_price:,} = {(quantity * product_price):,}\n"
    message += f"Jami summa: {total_sum:,}"
    return message, total_sum


def add_order_to_db(cart, total_sum, user_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT debt FROM users WHERE user_id=?", (user_id,))
    before_debt = c.fetchone()[0]
    print(before_debt)
    if before_debt is None:
        before_debt = 0
    total_debt = before_debt + total_sum
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_quantity = sum(cart.values())
    c.execute("INSERT INTO orders (user_id, total_sum, total_quantity, total_debt, order_date, before_order_debt) "
              "VALUES (?, ?, ?, ?, ?, ?)", (user_id, total_sum, total_quantity, total_debt, date, before_debt))
    order_id = c.lastrowid
    for product_id, quantity in cart.items():
        price = c.execute("SELECT product_price FROM products WHERE product_id=?", (product_id,)).fetchone()[0]
        c.execute("INSERT INTO itemInOrder (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)",
                  (order_id, product_id, quantity, price))
    c.execute("UPDATE users SET debt=? WHERE user_id=?", (total_debt, user_id))
    conn.commit()
    conn.close()


def get_user_telegram_id(user_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE user_id=?", (user_id,))
    telegram_id = c.fetchone()
    conn.close()
    return telegram_id[0] if telegram_id else None


def order_receipt_str(order_id):
    conn = create_db_connection()
    c = conn.cursor()
    
    # Fetch the order details
    c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
    order = c.fetchone()

    # Fetch the product details from itemInOrder (use itemInOrder.product_name to avoid ambiguity)
    c.execute("""
        SELECT itemInOrder.product_name, itemInOrder.quantity, itemInOrder.price 
        FROM itemInOrder
        WHERE itemInOrder.order_id=?
    """, (order_id,))
    products = c.fetchall()
    conn.close()

    # Format the receipt
    message = f"Buyurtma ID: {order[0]}\n"
    message += f"Sana: {order[2]}\n\n"
    message += "Mahsulotlar:\n"
    for product in products:
        message += f"{product[0]}: {product[1]} x {product[2]:,} = {(product[1] * product[2]):,}\n"
    message += f"\nJami summa: {order[3]:,}\n"
    message += f"Jami miqdor: {order[4]:,}\n"
    message += f"Oldindan bor qarz: {order[6]:,}\n"
    message += f"Jami qarz: {order[5]:,}\n"
    return message


# Step 6: Handle the confirmation of the order
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'confirming_order')
def handle_confirm_order(message):
    user_id = str(message.from_user.id)
    selected_user_id = admin_selected_clients.get(user_id)

    if message.text == "Ha":
        cart = user_cart[selected_user_id]

        # Convert cart to product list
        products = []
        for product_id, quantity in cart.items():
            conn = create_db_connection()
            c = conn.cursor()
            c.execute("SELECT product_name, product_price FROM products WHERE product_id=?", (product_id,))
            product_data = c.fetchone()
            conn.close()
            if product_data:
                product_name, product_price = product_data
                products.append({
                    'product_name': product_name,
                    'product_price': product_price,
                    'product_quantity': quantity
                })

        total_sum = sum(p['product_price'] * p['product_quantity'] for p in products)
        total_quantity = sum(p['product_quantity'] for p in products)
        before_order_debt = get_user_debt(selected_user_id)
        print(before_order_debt, selected_user_id)
        if before_order_debt is None:
            before_order_debt = 0
        total_debt = before_order_debt + total_sum

        # Add order
        new_order_id = add_order(
            user_id=selected_user_id,
            saved_name="",
            debt=total_debt,
            order_date=datetime.now().strftime("%Y-%m-%d"),
            products=products,
            total_sum=total_sum,
            total_quantity=total_quantity,
            total_debt=total_debt,
            before_order_debt=before_order_debt
        )

        # Notify admin about pending confirmation
        bot.send_message(message.chat.id, "Buyurtma muvaffaqiyatli qo`shildi. Tasdiqlash uchun mijozga yuborildi.")

        client_telegram_id = get_user_telegram_id(selected_user_id)
        if client_telegram_id:
            order_receipt = order_receipt_str(new_order_id)
            confirm_buttons = InlineKeyboardMarkup()
            confirm_buttons.add(InlineKeyboardButton("Tasdiqlash", callback_data=f"confirm_order_{new_order_id}"))
            bot.send_message(client_telegram_id, order_receipt, reply_markup=confirm_buttons)
            user_states[client_telegram_id] = 'confirming_order'
        user_states[user_id] = "awaiting_order_confirmation"
        back_to_menu(message)

    elif message.text == "Yo'q":
        bot.send_message(message.chat.id, "Buyurtma bekor qilindi.")
        user_states[user_id] = None
        back_to_menu(message)


# Step 7: Handle the confirmation of the order by the client
@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_order_"))
def handle_confirm_order_callback(call):
    order_id = int(call.data.split("_")[-1])

    conn = create_db_connection()
    c = conn.cursor()

    # Check if already confirmed
    c.execute("SELECT is_confirmed FROM orders WHERE order_id=?", (order_id,))
    is_confirmed = c.fetchone()[0]

    if is_confirmed:
        bot.answer_callback_query(call.id, "Bu buyurtma allaqachon tasdiqlangan.")
        return

    # Confirm the order
    c.execute("UPDATE orders SET is_confirmed=1 WHERE order_id=?", (order_id,))
    conn.commit()

    # Get order details for confirmation message
    order_summary = order_receipt_str(order_id)

    # Notify the client with the order details
    bot.edit_message_text(
        text=f"✅ Buyurtma tasdiqlandi!\n\n{order_summary}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="Markdown"
    )

    # Notify the admin(s)
    c.execute("SELECT telegram_id FROM users WHERE type='admin'")
    admins = c.fetchall()
    conn.close()

    if admins:
        for admin in admins:
            bot.send_message(admin[0], f"📢 *Buyurtma tasdiqlandi!*\n\n{order_summary}", parse_mode="Markdown")

    bot.answer_callback_query(call.id, "Buyurtma tasdiqlandi.")


def order_receipt_str(order_id):
    conn = create_db_connection()
    c = conn.cursor()

    # Fetch order details
    c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
    order = c.fetchone()

    if not order:
        conn.close()
        return "Buyurtma topilmadi."

    order_id, user_id, order_date, total_sum, total_quantity, total_debt, before_order_debt, is_confirmed = order

    # Fetch products in the order
    c.execute("""
        SELECT itemInOrder.product_name, itemInOrder.quantity, itemInOrder.price 
        FROM itemInOrder
        WHERE itemInOrder.order_id=?
    """, (order_id,))
    products = c.fetchall()
    conn.close()

    # Format the receipt message
    message = f"📦 Buyurtma ID: {order_id}\n📅 Sana: {order_date}\n\n"
    message += "🛍 Mahsulotlar:\n"
    for product in products:
        product_name, quantity, price = product
        total_price = quantity * price
        message += f"- {product_name}: {quantity} x {price:,} = {total_price:,} so'm\n"

    message += f"\n💰 Jami summa: {total_sum:,} so'm\n"
    message += f"📦 Jami miqdor: {total_quantity}\n"
    message += f"📉 Oldindan bor qarz: {before_order_debt:,} so'm\n"
    message += f"💳 Jami qarz: {total_debt:,} so'm\n"

    return message




# Example of using delete_order function
@bot.message_handler(func=lambda message: message.text == "/delete_order" or message.text == "Buyurtmani o'chirish")
@user_command_wrapper
def handle_delete_order(message):
    user_id = str(message.from_user.id)
    client_choice = message.text.strip()

    if client_choice == "Bosh menyu":
        # Clear the state and navigate back to the main menu
        user_states[user_id] = None
        print(f"Debug: User {user_id} selected 'Bosh menyu', resetting state and returning to menu.")
        back_to_menu(message)
        return

    if client_choice in commands_list:
        redirect_to_command(message)
        return

    if is_admin(user_id):
        clients = list_clients()

        if clients:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for client_id, client_data in clients.items():
                if client_data['last_name'] == '' or client_data['last_name'] is None:
                    markup.add(KeyboardButton(f"{client_data['first_name']} ({client_id})"))
                else:
                    markup.add(KeyboardButton(f"{client_data['first_name']} {client_data['last_name']} ({client_id})"))
            markup.add(KeyboardButton("Bosh menyu"))

            user_states[user_id] = 'selecting_client_for_order_deletion'
            bot.send_message(message.chat.id, "Mijozni tanlang", reply_markup=markup)
        else:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Bosh menyu"))

            # Reset the state and notify the user
            user_states[user_id] = None
            print(f"Debug: No clients found for user {user_id}.")
            bot.send_message(message.chat.id, "Bunday mijozlar topilmadi.", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Sizda buyurtmani o`chirishga ruxsat yo`q.")


# Catch-all handler for "Bosh menyu" in case of state inconsistencies
@bot.message_handler(func=lambda message: message.text == "Bosh menyu")
def handle_main_menu_navigation(message):
    user_id = str(message.from_user.id)
    print(f"Debug: User {user_id} pressed 'Bosh menyu'. Returning to main menu.")
    user_states[user_id] = None  # Reset the state
    back_to_menu(message)



# Handle the selection of a client for deleting an order
@bot.message_handler(
    func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_client_for_order_deletion')
@user_command_wrapper
def handle_select_client_for_order_deletion(message):
    user_id = str(message.from_user.id)
    client_choice = message.text.strip()

    if client_choice == "Bosh menyu":
        # Go to the main menu from the client list
        print(f"Debug: User {user_id} selected 'Bosh menyu' - returning to main menu")
        user_states[user_id] = None
        back_to_menu(message)
        return

    if client_choice in commands_list:
        redirect_to_command(message)
        return

    try:
        # Ensure the client choice contains a valid client ID
        if "(" not in client_choice or ")" not in client_choice:
            bot.send_message(message.chat.id, "Mijoz tanlash noto'g'ri. Qayta urinib ko'ring.")
            return

        # Extract client ID from the selected text (the ID is in parentheses)
        selected_client_id = client_choice.split('(')[-1].strip(')')
        print(f"Debug: Extracted Selected Client ID: {selected_client_id}")
        admin_selected_clients[user_id] = selected_client_id

        # Fetch orders by user_id (client ID in this case)
        orders = fetch_orders_by_user_id(selected_client_id)
        print(f"Debug: Fetched Orders for Client ID {selected_client_id}: {orders}")

        if orders:
            # Create a ReplyKeyboardMarkup for the orders
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for order in orders:
                try:
                    order_id = order[0]
                    order_date = parse_date_safe(order[2])
                    order_total = order[3]
                    markup.add(KeyboardButton(f"Buyurtma ID: {order_id}, Miqdor: {order_total:,}, Sana: {order_date}"))
                except Exception as e:
                    print(f"Error processing order {order}: {e}")

            # Add the "Bosh menyu" button
            markup.add(KeyboardButton("Bosh menyu"))

            # Update user state and send the menu
            user_states[user_id] = 'selecting_order_for_deletion'
            bot.send_message(message.chat.id, "O'chirish uchun buyurtmani tanlang:", reply_markup=markup)
        else:
            # No orders found, provide a fallback menu
            print(f"Debug: No orders found for Client ID {selected_client_id}")
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Bosh menyu"))
            bot.send_message(message.chat.id, "Mijozda buyurtmalar topilmadi.", reply_markup=markup)

    except Exception as e:
        print(f"Error while selecting client for order deletion: {e}")
        bot.send_message(message.chat.id, f"Mijoz noto'g'ri tanlangan: {e}")


def show_clients_list(message):
    """
    Show the list of clients to the admin for selection.
    """
    user_id = str(message.from_user.id)

    try:
        # Fetch the list of clients
        conn = create_db_connection()
        c = conn.cursor()
        c.execute("SELECT user_id, first_name, last_name FROM users WHERE type='client'")
        clients = c.fetchall()
        conn.close()

        if clients:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for client in clients:
                client_id, first_name, last_name = client
                markup.add(KeyboardButton(f"{first_name} {last_name} ({client_id})"))
            markup.add(KeyboardButton("Bosh menyu"))
            user_states[user_id] = 'selecting_client_for_order_deletion'
            bot.send_message(message.chat.id, "Mijozni tanlang:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Mijozlar topilmadi.")
    except Exception as e:
        print(f"Error fetching clients: {e}")
        bot.send_message(message.chat.id, f"Mijozlar ro'yxatini yuklashda xatolik: {e}")


def parse_date_safe(date_str):
    try:
        # Try parsing with date and time
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S').strftime('%d/%m/%Y')
    except ValueError:
        try:
            # Fallback to date-only parsing
            return datetime.strptime(date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
        except ValueError:
            return "Noma'lum sana"  # Fallback if both fail

def fetch_orders_by_user_id(user_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE user_id = ?", (user_id,))
    orders = c.fetchall()
    conn.close()
    return orders



def get_order_by_id(order_id):
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT orders.order_id, orders.user_id, orders.order_date, 
               orders.total_sum, orders.total_quantity, 
               orders.total_debt, orders.before_order_debt, orders.is_confirmed
        FROM orders 
        WHERE orders.order_id=?
    """, (order_id,))
    order = c.fetchone()
    conn.close()
    return order


def delete_order_by_id(order_id):
    conn = create_db_connection()
    c = conn.cursor()

    # Fetch user_id and order_total_sum for updating user's debt
    c.execute("SELECT user_id, total_sum FROM orders WHERE order_id=?", (order_id,))
    user_id, order_total_sum = c.fetchone()

    # Delete items in the order
    c.execute("DELETE FROM itemInOrder WHERE order_id=?", (order_id,))

    # Delete the order itself
    c.execute("DELETE FROM orders WHERE order_id=?", (order_id,))

    # Update the user's debt
    c.execute("UPDATE users SET debt=debt-? WHERE user_id=?", (order_total_sum, user_id))
    conn.commit()
    conn.close()


# Handle the selection of an order for deletion
@bot.message_handler(
    func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_order_for_deletion')
@user_command_wrapper
def handle_select_order_for_deletion(message):
    user_id = str(message.from_user.id)
    order_choice = message.text.strip()

    if order_choice == "Bosh menyu":
        # Go back to the client list from the order list
        print(f"Debug: User {user_id} selected 'Bosh menyu' - returning to client list")
        user_states[user_id] = 'selecting_client_for_order_deletion'
        show_clients_list(message)  # Function to show the list of clients
        return

    if order_choice in commands_list:
        redirect_to_command(message)
        return

    try:
        # Ensure the order choice contains a valid order ID
        if "Buyurtma ID:" not in order_choice:
            bot.send_message(message.chat.id, "Buyurtma tanlash noto'g'ri. Qayta urinib ko'ring.")
            return

        # Extract order ID from the selected text
        selected_order_id = int(order_choice.split(':')[1].split(',')[0].strip())
        print(f"Debug: Extracted Selected Order ID: {selected_order_id}")

        # Confirm deletion
        delete_order_by_id(selected_order_id)  # Function to delete the order
        bot.send_message(message.chat.id, f"Buyurtma ID: {selected_order_id} muvaffaqiyatli o'chirildi.")
        back_to_menu(message)

    except Exception as e:
        print(f"Error while selecting order for deletion: {e}")
        bot.send_message(message.chat.id, f"Buyurtma noto'g'ri tanlangan: {e}")


def get_client_full_name(user_id):
    """
    Retrieve the full name of a client from the database.
    Handles cases where first_name or last_name may be NULL.
    """
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT first_name, last_name FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()

    if result:
        first_name, last_name = result
        # Combine first_name and last_name, ignoring NULL (None) values
        full_name = f"{first_name or ''} {last_name or ''}".strip()
        return full_name if full_name else "Noma'lum"
    return "Noma'lum"


# Handle the /list_orders command
@bot.message_handler(func=lambda message: message.text == "/list_orders" or message.text == "Buyurtmalarni ko'rish")
@user_command_wrapper
def handle_list_orders(message):
    user_id = str(message.from_user.id)

    # Check if the user is a client
    if is_client(user_id):
        orders_list = list_orders_db(message.from_user.id)
        if orders_list:
            message_text = "Sizning buyurtmalaringiz:\n\n"
            for order in orders_list:
                order_id, user_id, order_date, total_sum, total_quantity, total_debt, before_order_debt, is_confirmed = order
                order_date = parse_date_safe(order_date)

                # Fetch products for the order
                conn = create_db_connection()
                c = conn.cursor()
                c.execute("""
                    SELECT product_name, quantity, product_price 
                    FROM itemInOrder 
                    WHERE order_id = ?
                """, (order_id,))
                products = c.fetchall()
                conn.close()

                # Format product list
                product_details = "\n".join([
                    f"{product[0]} ({product[1]} x {product[2]:,})"
                    for product in products
                ])

                # Append order details to message
                message_text += (
                    f"Buyurtma ID: {order_id}\n"
                    f"Sana: {order_date}\n"
                    f"Mahsulotlar:\n{product_details}\n"
                    f"\nBuyurtmadan oldingi qarz: {before_order_debt:,} so'm\n"
                    f"Jami buyurtma summasi: {total_sum:,} so'm\n"
                    f"Buyurtmadan keyengi qarz: {total_debt:,} so'm\n"
                    f"Tasdiqlangan: {'Ha' if is_confirmed else 'Yoq'}\n\n\n"
                )
            bot.send_message(message.chat.id, message_text)
        else:
            bot.send_message(message.chat.id, "Sizning buyurtmalaringiz topilmadi.")

    elif is_admin(user_id):
        orders_list = list_orders_db_admin()
        if orders_list:
            message_text = "Barcha buyurtmalar:\n\n"
            for order in orders_list:
                order_id, user_id, order_date, total_sum, total_quantity, total_debt, before_order_debt, is_confirmed = order
                order_date = parse_date_safe(order_date)

                # Fetch products for the order
                conn = create_db_connection()
                c = conn.cursor()
                c.execute("""
                    SELECT product_name, quantity, product_price 
                    FROM itemInOrder 
                    WHERE order_id = ?
                """, (order_id,))
                products = c.fetchall()
                conn.close()

                # Format product list
                product_details = "\n".join([
                    f"{product[0]} ({product[1]} x {product[2]:,})"
                    for product in products
                ])
                full_name = get_client_full_name(user_id)

                # Append order details to message
                message_text += (
                    f"Mijoz: {full_name or 'Nomalum'}\n"
                    f"Buyurtma ID: {order_id}\n"
                    f"Sana: {order_date}\n"
                    f"Mahsulotlar:\n{product_details}\n"
                    f"\nBuyurtmadan oldingi qarz: {before_order_debt:,} so'm\n"
                    f"Jami buyurtma summasi: {total_sum:,} so'm\n"
                    f"Buyurtmadan keyengi qarz: {total_debt:,} so'm\n"
                    f"Tasdiqlangan: {'Ha' if is_confirmed else 'Yoq'}\n\n\n"
                )
            bot.send_message(message.chat.id, message_text)
        else:
            bot.send_message(message.chat.id, "Buyurtmalar topilmadi.")
    else:
        bot.send_message(message.chat.id, "Sizda buyurtmalarni ko'rish uchun ruxsat yo'q.")

    back_to_menu(message)



# Handle the /list_products command
@bot.message_handler(commands=['list_products'])
@user_command_wrapper
def handle_list_products(message):
    user_id = str(message.from_user.id)
    command_parts = message.text.split()

    if len(command_parts) < 2:
        bot.send_message(message.chat.id, "Buyurtma ID ni kiritish kerak. Masalan: /list_products 1")
        return

    order_id = command_parts[1]  # Extract order ID from the message

    if is_admin(user_id):
        conn = create_db_connection()
        c = conn.cursor()

        # Fetch all clients for admin
        c.execute("SELECT user_id, first_name, last_name FROM users WHERE type='client'")
        clients = c.fetchall()
        conn.close()

        # Iterate through clients and their orders
        for client_id, first_name, last_name in clients:
            conn = create_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM orders WHERE user_id=?", (client_id,))
            orders = c.fetchall()
            conn.close()

            # Check if the order ID matches
            for order in orders:
                if str(order[0]) == order_id:  # Assuming order[0] is the order_id column
                    before_order_debt = order[6]  # Assuming order[6] is the before_order_debt column
                    total_sum = order[3]  # Assuming order[3] is the total_sum column

                    # Fetch products associated with this order
                    conn = create_db_connection()
                    c = conn.cursor()
                    c.execute("""
                        SELECT p.product_name, io.quantity, io.price 
                        FROM itemInOrder io 
                        INNER JOIN products p ON io.product_id = p.product_id 
                        WHERE io.order_id=?
                    """, (order_id,))
                    products = c.fetchall()
                    conn.close()

                    # Prepare the product list
                    if products:
                        products_list = "\n".join([
                            f"Mahsulot: {product[0]}, Miqdori: {product[1]:,}, Narxi: {product[2]:,}"
                            for product in products
                        ])
                    else:
                        products_list = "Mahsulotlar topilmadi."

                    # Prepare and send the final message
                    products_list = (
                        f"Mijoz: {first_name or ''} {last_name or ''}\n"
                        f"Savdodan avvalgi qarz: {before_order_debt} сўм\n\n"
                        + products_list
                        + f"\n\nJami summa: {total_sum} сўм"
                    )
                    bot.send_message(message.chat.id, products_list)
                    return

        # If no matching order is found
        bot.send_message(message.chat.id, f"Buyurtma ID {order_id} topilmadi.")

    elif is_client(user_id):
        # Clients can only list their own products
        conn = create_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM orders WHERE user_id=? AND order_id=?", (user_id, order_id))
        order = c.fetchone()

        if order:
            before_order_debt = order[6]  # Assuming order[6] is the before_order_debt column
            total_sum = order[3]  # Assuming order[3] is the total_sum column

            # Fetch products associated with this order
            conn = create_db_connection()
            c = conn.cursor()
            c.execute("""
                SELECT p.product_name, io.quantity, io.price 
                FROM itemInOrder io 
                INNER JOIN products p ON io.product_id = p.product_id 
                WHERE io.order_id=?
            """, (order_id,))
            products = c.fetchall()
            conn.close()

            # Prepare the product list
            if products:
                products_list = "\n".join([
                    f"Mahsulot: {product[0]}, Miqdori: {product[1]:,}, Narxi: {product[2]:,}"
                    for product in products
                ])
            else:
                products_list = "Mahsulotlar topilmadi."

            # Prepare and send the final message
            products_list = (
                f"Savdodan avvalgi qarz: {before_order_debt} сўм\n\n"
                + products_list
                + f"\n\nJami summa: {total_sum} сўм"
            )
            bot.send_message(message.chat.id, products_list)
        else:
            bot.send_message(message.chat.id, f"Buyurtma ID {order_id} topilmadi.")
    else:
        bot.send_message(message.chat.id, "Sizda buyurtmalarni ko'rishga ruxsat yo'q.")


@bot.message_handler(func=lambda message: message.text == "To'lovni amalga oshirish")
def handle_payment_button(message):
    handle_pay_debt(message)  # Reuse the /pay_debt logic
            

def list_admins():
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE type='admin'")
    admins = c.fetchall()
    conn.close()
    
    if not admins:
        print("No admins found in the database.")
        return []
    
    # Debug: Log the admin IDs
    admin_ids = [admin[0] for admin in admins]
    print(f"Admin IDs: {admin_ids}")
    return admin_ids


# Add a table for payments
def create_payments_table():
    conn = create_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS payments
                 (payment_id INTEGER PRIMARY KEY, user_id INTEGER, amount INTEGER, is_confirmed INTEGER DEFAULT 0,
                  FOREIGN KEY(user_id) REFERENCES users(user_id))''')
    conn.commit()
    conn.close()


# Handle the /pay_debt command
@bot.message_handler(commands=['pay_debt'])
def handle_pay_debt(message):
    user_id = str(message.from_user.id)
    if is_client(user_id):
        bot.send_message(message.chat.id, "To'lagan summangizni kiriting:")
        user_states[user_id] = 'awaiting_payment_amount'
    else:
        bot.send_message(message.chat.id, "Siz mijoz emassiz. Ushbu buyruq faqat mijozlar uchun mavjud.")


# Receive payment amount
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'awaiting_payment_amount')
def receive_payment_amount(message):
    user_id = str(message.from_user.id)
    try:
        amount = int(message.text.strip())

        if amount <= 0:
            bot.send_message(message.chat.id, "❌ To'lov miqdori noto'g'ri. Iltimos, qaytadan kiriting.")
            return

        # Store the amount and move to asking for comment
        user_states[user_id] = {'state': 'awaiting_payment_comment', 'amount': amount}
        bot.send_message(message.chat.id, "📝 To'lov uchun izoh kiriting (Majburiy emas). Agar izoh yo'q bo'lsa, 'Yoq' deb yozing.")

    except ValueError:
        bot.send_message(message.chat.id, "❌ Iltimos, to'lov miqdorini raqam sifatida kiriting.")


@bot.message_handler(func=lambda message: isinstance(user_states.get(str(message.from_user.id)), dict) and user_states[str(message.from_user.id)]['state'] == 'awaiting_payment_comment')
def receive_payment_comment(message):
    user_id = str(message.from_user.id)
    payment_data = user_states.get(user_id)

    if not payment_data or 'amount' not in payment_data:
        bot.send_message(message.chat.id, "❌ Xatolik yuz berdi. Iltimos, to'lovni qaytadan kiriting.")
        user_states[user_id] = None
        logging.warning(f"User {user_id} encountered an error: Missing payment data.")
        return

    amount = payment_data['amount']
    comment = message.text.strip()
    if comment.lower() == "yo'q":
        comment = "Izoh yo'q"

    try:
        # Store payment in database
        conn = create_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO payments (user_id, amount, is_confirmed, comment) VALUES (?, ?, ?, ?)", (user_id, amount, 0, comment))
        conn.commit()
        payment_id = c.lastrowid
        conn.close()

        logging.info(f"Payment received: User {user_id}, Amount: {amount}, Comment: {comment}")

        # Notify client
        bot.send_message(
            message.chat.id,
            f"✅ *To'lov qabul qilindi!* \n\n"
            f"💰 *Miqdor:* {amount:,} so'm \n"
            f"📝 *Izoh:* {comment} \n\n"
            f"⏳ Tasdiqlash kutilmoqda."
        )

        # Notify admins
        admins = list_admins()
        for admin in admins:
            confirm_buttons = InlineKeyboardMarkup()
            confirm_buttons.add(
                InlineKeyboardButton("Tasdiqlash", callback_data=f"confirm_payment_{payment_id}"),
                InlineKeyboardButton("Rad etish", callback_data=f"reject_payment_{payment_id}")
            )
            bot.send_message(admin, f"📢 *Yangi to'lov!* \n\n"
                                    f"👤 *Mijoz ID:* {user_id} \n"
                                    f"💰 *Miqdor:* {amount:,} so'm \n"
                                    f"📝 *Izoh:* {comment} \n\n"
                                    f"✅ Tasdiqlash yoki rad etish uchun tugmalardan foydalaning.", reply_markup=confirm_buttons)
        
        logging.info(f"Payment notification sent to admins for User {user_id}, Payment ID: {payment_id}")

        # Reset state
        user_states[user_id] = None
        back_to_menu(message)

    except Exception as e:
        logging.error(f"Error processing payment for User {user_id}: {e}", exc_info=True)
        bot.send_message(message.chat.id, "❌ Xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")



@bot.message_handler(func=lambda message: True)
def log_user_message(message):
    logging.info(f"User {message.from_user.id} sent: {message.text}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_payment_") or call.data.startswith("reject_payment_"))
def handle_payment_confirmation(call):
    payment_id = int(call.data.split("_")[-1])
    conn = create_db_connection()
    c = conn.cursor()

    # Check if already confirmed
    c.execute("SELECT is_confirmed FROM payments WHERE payment_id=?", (payment_id,))
    is_confirmed = c.fetchone()[0]

    if is_confirmed:
        bot.answer_callback_query(call.id, "Bu to'lov allaqachon tasdiqlangan.")
        return
    
    try:
        # Get user_id (telegram_id) and amount from the payments table
        c.execute("SELECT user_id, amount FROM payments WHERE payment_id=?", (payment_id,))
        payment = c.fetchone()

        if payment:
            telegram_id, amount = payment

            # Get the internal user_id and type from the users table using telegram_id
            c.execute("SELECT user_id, debt, type FROM users WHERE telegram_id=?", (telegram_id,))
            user_record = c.fetchone()

            if user_record:
                internal_user_id, current_debt, user_type = user_record

                if call.data.startswith("confirm_payment_"):
                    # Confirm payment
                    c.execute("UPDATE payments SET is_confirmed=1 WHERE payment_id=?", (payment_id,))

                    # Calculate the new debt
                    new_debt = current_debt - amount
                    if new_debt < 0:
                        new_debt = 0  # Ensure debt doesn't go negative

                    # Update the debt in the `users` table
                    c.execute("UPDATE users SET debt=? WHERE user_id=?", (new_debt, internal_user_id))

                    # Update total_debt in the orders table
                    c.execute("""
                        UPDATE orders
                        SET total_debt = ?
                        WHERE user_id=? AND is_confirmed=1
                    """, (new_debt, internal_user_id))
                    
                    conn.commit()  # Commit all changes

                    # Notify admin and the user
                    bot.edit_message_text(
                        text="✅ To'lov tasdiqlandi!",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id
                    )

                    admins = list_admins()
                    print(f"Admins: {admins}")
                    for admin in admins:
                        try:
                            bot.edit_message_text(
                                text="✅ To'lov tasdiqlandi!",
                                chat_id=admin[0],
                                message_id=call.message.message_id
                            )
                        except Exception as e:
                            print(f"Error updating message for admin {admin[0]}: {e}")

                    bot.answer_callback_query(call.id, "To'lov tasdiqlandi.")

                    if telegram_id:
                        bot.send_message(telegram_id, f"Sizning {amount:,} so'm to'lovingiz tasdiqlandi. Rahmat!")
                elif call.data.startswith("reject_payment_"):
                    # Reject payment
                    c.execute("DELETE FROM payments WHERE payment_id=?", (payment_id,))
                    conn.commit()

                    bot.send_message(call.message.chat.id, "To'lov rad etildi.")
                    if telegram_id:
                        bot.send_message(telegram_id, f"Sizning {amount:,} so'm to'lovingiz rad etildi.")
            else:
                bot.send_message(call.message.chat.id, "Foydalanuvchi topilmadi. To'lovni qayta tekshiring.")
        else:
            bot.send_message(call.message.chat.id, "To'lov topilmadi.")
    except Exception as e:
        conn.rollback()  # Rollback if any error occurs
        bot.send_message(call.message.chat.id, f"Xatolik yuz berdi: {str(e)}")
    finally:
        conn.close()  # Ensure the connection is always closed

    # Force correct menu based on user role
    conn = create_db_connection()
    c = conn.cursor()
    c.execute("SELECT type FROM users WHERE telegram_id=?", (call.from_user.id,))
    user_type = c.fetchone()
    conn.close()

    if user_type:
        if user_type[0] == "admin":
            # Admin menu
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Buyurtma qo'shish"), KeyboardButton("Buyurtmani o'chirish"))
            markup.add(KeyboardButton("Mijoz ma'lumotlarini o'zgartirish"), KeyboardButton("Mahsulotni tahrirlash"))
            markup.add(KeyboardButton("Buyurtmalarni ko'rish"))
            bot.send_message(call.message.chat.id, "Menyu", reply_markup=markup)
        else:
            # Client menu
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Buyurtmalarni ko'rish"))  # View orders
            markup.add(KeyboardButton("To'lovni amalga oshirish"))  # New payment button
            bot.send_message(call.message.chat.id, "Menyu", reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, "Foydalanuvchi turi aniqlanmadi.")





@bot.message_handler(func=lambda message: message.text == "/help")
@user_command_wrapper
def help(message):
    user_id = str(message.from_user.id)

    help_text = "Buyurtma tizimi uchun mavjud komandalar:\n\n"
    help_text += "/start - Ro'yxatdan o'tkazish yoki qayta kirish\n"
    help_text += "/help - Barcha mavjud komandalarni ko'rsatish\n"

    if is_admin(user_id):
        help_text += "/add_order - Buyurtma qo'shish (faqat adminlar uchun)\n"
        help_text += "/delete_order <order_id> - Buyurtmani ID bo'yicha o'chirish (faqat adminlar uchun)\n"
        help_text += "/edit_client - Mijoz ma'lumotlarini o'zgartirish (faqat adminlar uchun)\n"

    help_text += "/list_orders - Barcha buyurtmalarni ro'yxatini ko'rsatish\n"
    help_text += "/list_products <order_id> - Belgilangan buyurtma ID bo'yicha barcha mahsulotlarni ko'rsatish\n"

    bot.send_message(message.chat.id, help_text)


# Menu commands
def set_bot_commands(bot):
    commands = [
        BotCommand("start", "Ro'yxatdan o'tkazish yoki qayta kirish"),
        BotCommand("help", "Barcha mavjud komandalarni ko'rsatish"),
        BotCommand("add_order", "Buyurtma qo'shish (faqat adminlar uchun)"),
        BotCommand("delete_order", "Buyurtmani ID bo'yicha o'chirish (faqat adminlar uchun)"),
        BotCommand("edit_client", "Mijoz ma'lumotlarini o'zgartirish (faqat adminlar uchun)"),
        BotCommand("list_orders", "Barcha buyurtmalarni ro'yxatini ko'rsatish"),
        BotCommand("list_products", "Belgilangan buyurtma ID bo'yicha barcha mahsulotlarni ko'rsatish")
    ]
    bot.set_my_commands(commands)


if __name__ == "__main__":
    set_bot_commands(bot)
    bot.polling(none_stop=True)