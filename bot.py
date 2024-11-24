from datetime import datetime

import telebot
from telebot import types
from telebot.types import BotCommand, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from functools import wraps
import sqlite3

TOKEN = '7099572080:AAH6FYY_KDVrCgvhVa8CgV2ZdTIESi0JZEw'

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
        markup.add(KeyboardButton("Mijoz ma'lumotlarini o'zgartirish"), KeyboardButton("Buyurtmalarni ko'rish"))
        user_states[user_id] = None
        bot.send_message(message.chat.id, "Menyu", reply_markup=markup)
        print("Back to menu")
    else:
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton("Buyurtmalarni ko'rish"))
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
        admin_selected_clients[user_id] = selected_client_id

        # Display the current client data
        client_data = get_client_by_id(selected_client_id)
        client_info = (
            f"Mijoz haqida:\n"
            f"Username: {client_data[1]}\n"
            f"Ism: {client_data[2]}\n"
            f"Familiya: {client_data[3]}\n"
            f"Sistemadagi Ism: {client_data[5]}\n"
            f"Qarzi: {client_data[6]}\n"
            f"Type: {client_data[4]}\n"
        )
        bot.send_message(message.chat.id, client_info)

        # Ask admin which field they want to edit
        markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(KeyboardButton("Username"), KeyboardButton("Ism"), KeyboardButton("Familiya"))
        markup.add(KeyboardButton("Sistemadagi Ism"), KeyboardButton("Qarzi"), KeyboardButton("Type"))
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
    else:
        bot.send_message(message.chat.id, "Invalid choice. Please select a valid field.")


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
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) and user_states.get(
    str(message.from_user.id)).startswith('editing'))
def handle_edit_field(message):
    user_id = str(message.from_user.id)
    selected_client_id = admin_selected_clients.get(user_id)
    new_value = message.text.strip()

    if new_value == "Bosh menyu":
        back_to_menu(message)
        return

    if new_value in commands_list:
        redirect_to_command(message)
        return

    if selected_client_id:
        client_data = get_client_by_id(selected_client_id)

        # Update the correct field based on the state
        state = user_states[user_id]
        conn = create_db_connection()
        c = conn.cursor()
        if state == 'editing_username':
            c.execute("UPDATE users SET username=? WHERE user_id=?", (new_value, selected_client_id))
            bot.send_message(message.chat.id, f"Username o`zgartirildi '{new_value}'.")
            back_to_menu(message)
        elif state == 'editing_ism':
            c.execute("UPDATE users SET first_name=? WHERE user_id=?", (new_value, selected_client_id))
            bot.send_message(message.chat.id, f"Ism o`zgartirildi '{new_value}'.")
            back_to_menu(message)
        elif state == 'editing_familiya':
            c.execute("UPDATE users SET last_name=? WHERE user_id=?", (new_value, selected_client_id))
            bot.send_message(message.chat.id, f"Familiya o`zgartirildi '{new_value}'.")
            back_to_menu(message)
        elif state == 'editing_sistemadagi_ism':
            c.execute("UPDATE users SET saved_name=? WHERE user_id=?", (new_value, selected_client_id))
            bot.send_message(message.chat.id, f"Sistemadagi ism o`zgartirildi '{new_value}'.")
            back_to_menu(message)
        elif state == 'editing_qarzi':
            try:
                new_value = int(new_value)
                c.execute("UPDATE users SET debt=? WHERE user_id=?", (new_value, selected_client_id))
                bot.send_message(message.chat.id, f"Qarz o`zgartirildi {new_value}.")
                back_to_menu(message)
            except ValueError:
                bot.send_message(message.chat.id, "Qarzni noto`g`ri kiritdingiz. Iltimos, qaytadan kiriting.")
                back_to_menu(message)
        elif state == 'editing_type':
            if new_value in ['Admin', 'Client']:
                c.execute("UPDATE users SET type=? WHERE user_id=?", (new_value.lower(), selected_client_id))
                bot.send_message(message.chat.id, f"User type o`zgartirildi '{new_value.lower()}'.")
                back_to_menu(message)
            else:
                bot.send_message(message.chat.id, "Typeni noto`g`ri kiritdingiz. Iltimos, qaytadan kiriting.")
                back_to_menu(message)

        # Save the updated data
        conn.commit()
        conn.close()


        # Reset state
        user_states[user_id] = None
        admin_selected_clients[user_id] = None

    else:
        bot.send_message(message.chat.id, "Mijoz tanlanmangan. Iltimos, qaytadan urinib ko`ring.")


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
    
    # Fetch the user data
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user_data = c.fetchone()
    conn.close()

    # Ensure user_data is a tuple and process it accordingly
    if user_data:
        # Add the new order to the database
        conn = create_db_connection()
        c = conn.cursor()
        c.execute(
            "INSERT INTO orders (user_id, order_date, total_sum, total_quantity, total_debt, before_order_debt, is_confirmed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, order_date, total_sum, total_quantity, total_debt, before_order_debt, 0)
        )
        order_id = c.lastrowid  # Get the ID of the newly inserted order

        # Insert each product into the itemInOrder table
        for product in products:
            product_id = get_product_id_by_name(product['product_name'])
            c.execute(
                "INSERT INTO itemInOrder (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)",
                (order_id, product_id, product['product_quantity'], product['product_price'])
            )

        # Update the user's debt in the database
        c.execute("UPDATE users SET debt=? WHERE user_id=?", (total_debt, user_id))
        conn.commit()
        conn.close()

        print(f"Order added for user {user_id}: Order ID {order_id}")
    else:
        print(f"User {user_id} not found.")



def print_orders(orders):
    message = ""
    for order in orders:
        formatted_total_sum = "{:,}".format(order['total_sum']).replace(",", " ")
        message += f"Buyurtma ID: {order['order_id']}, miqdor: {formatted_total_sum}, sana: {order['order_date']} "
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
                message += (f"Buyurtma ID: {order['order_id']}, Miqdor: {formatted_total_sum} so'm, "
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
    c.execute("SELECT debt FROM users WHERE telegram_id=?", (user_id,))
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
                        f"Miqdori: {product['product_quantity']}"
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
    markup.add(KeyboardButton("Bosh menyu"))
    markup.add(KeyboardButton("Mahsulot qo'shish"))
    markup.add(KeyboardButton("Buyurtma yig'ildi"))
    return markup


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
        c.execute("INSERT INTO products (product_name, product_price) VALUES (?, ?)", (product_name, product_price))
        conn.commit()
        conn.close()
        keyboard = products_list_keyboard()
        bot.send_message(message.chat.id, "Yangi mahsulot muvaffaqiyatli qo`shildi.", reply_markup=keyboard)
        user_states[user_id] = 'awaiting_order_data'
    except Exception as e:
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
        message += f"{product_name}: {quantity} x {product_price} = {quantity * product_price}\n"
    message += f"Jami summa: {total_sum}"
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
        total_debt = before_order_debt + total_sum

        # Add order
        add_order(
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

        bot.send_message(message.chat.id, "Buyurtma muvaffaqiyatli qo`shildi.")
        user_states[user_id] = None
        back_to_menu(message)

    elif message.text == "Yo'q":
        bot.send_message(message.chat.id, "Buyurtma bekor qilindi.")
        user_states[user_id] = None
        back_to_menu(message)



# Example of using delete_order function
@bot.message_handler(func=lambda message: message.text == "/delete_order" or message.text == "Buyurtmani o'chirish")
@user_command_wrapper
def handle_delete_order(message):
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

            user_states[user_id] = 'selecting_client_for_order_deletion'
            bot.send_message(message.chat.id, "Mijozni tanlang", reply_markup=markup)
        else:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Bosh menyu"))
            bot.send_message(message.chat.id, "Bunday mijozlar topilmadi.", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Sizda buyurtmani o`chirishga ruxsat yo`q.")


# Handle the selection of a client for deleting an order
@bot.message_handler(
    func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_client_for_order_deletion')
@user_command_wrapper
def handle_select_client_for_order_deletion(message):
    if message.text == "Bosh menyu":
        back_to_menu(message)
        return

    if message.text in commands_list:
        redirect_to_command(message)
        return

    user_id = str(message.from_user.id)
    client_choice = message.text.strip()

    try:
        # Extract client ID from the selected text (the ID is in parentheses)
        selected_client_id = client_choice.split('(')[-1].strip(')')
        print(f"Debug: Extracted Selected Client ID: {selected_client_id}")
        admin_selected_clients[user_id] = selected_client_id

        # Fetch orders by user_id (client ID in this case)
        orders = fetch_orders_by_user_id(selected_client_id)  # New function to fetch orders directly by user_id
        print(f"Debug: Fetched Orders for Client ID {selected_client_id}: {orders}")

        if orders:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for order in orders:
                markup.add(KeyboardButton(
                    f"Buyurtma ID: {order[0]}, Miqdor: {order[3]}, Sana: {parse_date_safe(order[2])}"))
            markup.add(KeyboardButton("Bosh menyu"))
            user_states[user_id] = 'selecting_order_for_deletion'
            bot.send_message(message.chat.id, "O'chirish uchun buyurtmani tanlang:", reply_markup=markup)
        else:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Bosh menyu"))
            bot.send_message(message.chat.id, "Mijozda buyurtmalar topilmadi.", reply_markup=markup)

    except Exception as e:
        bot.send_message(message.chat.id, f"Mijoz noto`g`ri tanlangan: {e}")

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
    c.execute("SELECT * FROM orders WHERE order_id=?", (order_id,))
    order = c.fetchone()
    conn.close()
    return order


def delete_order_by_id(order_id):
    conn = create_db_connection()
    c = conn.cursor()
    user_id, order_total_sum = c.execute("SELECT user_id, total_sum FROM orders WHERE order_id=?", (order_id,)).fetchone()
    c.execute("DELETE FROM itemInOrder WHERE order_id=?", (order_id,))
    c.execute("DELETE FROM orders WHERE order_id=?", (order_id,))
    c.execute("UPDATE users SET debt=debt-? WHERE user_id=?", (order_total_sum, user_id))
    conn.commit()
    conn.close()

# Handle the selection of an order to delete
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_order_for_deletion')
@user_command_wrapper
def handle_select_order_for_deletion(message):
    user_id = str(message.from_user.id)
    order_choice = message.text.strip()

    try:
        # Extract order ID from the selected text
        selected_order_id = order_choice.split(',')[0].split()[-1]
        selected_client_id = admin_selected_clients.get(user_id)

        if selected_client_id:
            # Filter the order to be deleted
            new_orders = get_order_by_id(selected_order_id)
            print(new_orders)

            if not new_orders:
                bot.send_message(message.chat.id, f"Buyurtma {selected_order_id} topilmadi.")
            else:
                delete_order_by_id(selected_order_id)
                bot.send_message(message.chat.id, f"Buyurtma {selected_order_id} muvaffaqiyatli o`chiirildi.")
                back_to_menu(message)
        else:
            bot.send_message(message.chat.id, "Mijoz tanlanmagan. Iltimos, qaytadan urinib ko`ring.")
    except Exception as e:
        bot.send_message(message.chat.id, f"Buyurtmani o`chirib bo`lmadi: {e}")

        # Reset state
        user_states[user_id] = None
        admin_selected_clients[user_id] = None


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
        # Retrieve the client's orders from the database
        orders_list = list_orders_db(user_id)
        if orders_list:
            message_text = f"Sizning buyurtmalaringiz:\n\n"
            for order in orders_list:
                order_id, user_id, order_date, total_sum, total_quantity, total_debt, before_order_debt, is_confirmed = order
                formatted_order = (
                    f"Buyurtma ID: {order_id}\n"
                    f"Sana: {order_date}\n"
                    f"Jami summa: {total_sum:,} so'm\n"
                    f"Miqdor: {total_quantity}\n"
                    f"Qarzdan oldingi holat: {before_order_debt:,} so'm\n"
                    f"Tasdiq: {'Ha' if is_confirmed else 'Yo`q'}\n\n"
                )
                message_text += formatted_order
            bot.send_message(message.chat.id, message_text)
        else:
            bot.send_message(message.chat.id, "Sizning buyurtmalaringiz topilmadi.")

    elif is_admin(user_id):
        # Admins can list all orders
        orders_list = list_orders_db_admin()
        if orders_list:
            message_text = "Barcha buyurtmalar:\n\n"
            for order in orders_list:
                order_id, user_id, order_date, total_sum, total_quantity, total_debt, before_order_debt, is_confirmed = order
                full_name = get_client_full_name(user_id)
                formatted_order = (
                    f"Mijoz: {full_name or 'Noma`lum'}\n"
                    f"Buyurtma ID: {order_id}\n"
                    f"Sana: {order_date}\n"
                    f"Jami summa: {total_sum:,} so'm\n"
                    f"Miqdor: {total_quantity}\n"
                    f"Qarzdan oldingi holat: {before_order_debt:,} so'm\n"
                    f"Tasdiq: {'Ha' if is_confirmed else 'Yo`q'}\n\n"
                )
                message_text += formatted_order
            bot.send_message(message.chat.id, message_text)
        else:
            bot.send_message(message.chat.id, "Buyurtmalar topilmadi.")
    else:
        # If the user is neither a client nor an admin
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
                            f"Mahsulot: {product[0]}, Miqdori: {product[1]}, Narxi: {product[2]}"
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
                    f"Mahsulot: {product[0]}, Miqdori: {product[1]}, Narxi: {product[2]}"
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