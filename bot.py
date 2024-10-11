import json
import telebot
from telebot import types
from telebot.types import BotCommand, ReplyKeyboardMarkup, KeyboardButton
from functools import wraps

TOKEN = '7099572080:AAH6FYY_KDVrCgvhVa8CgV2ZdTIESi0JZEw'

bot = telebot.TeleBot(TOKEN)

# Dictionary to keep track of which users are expected to provide data
user_states = {}
admin_selected_clients = {}  # To keep track of the client selected by the admin for adding an order

commands_list = [
    "/start", "/help", "/add_order", "/delete_order", "/edit_client", "/list_orders", "/list_products"
]


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
            bot.send_message(message.chat.id, "Sizning profilingiz topilmadi. Iltimos, foydalanishni boshlash uchun /start ni kiriting.")
        else:
            func(message)
    return wrapper


# Функция для загрузки данных из JSON-файла
def load_data(filename):
    try:
        with open(filename, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


# Функция для сохранения данных в JSON-файл
def save_data(filename, data):
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)


# Check if user is an admin
def is_admin(user_id):
    data = load_data('data.json')
    user_data = data.get(user_id, {})
    return user_data.get('type') == 'admin'


# Check if user is a client
def is_client(user_id):
    data = load_data('data.json')
    user_data = data.get(user_id, {})
    return user_data.get('type') == 'client'


# Function to list all clients for admin to select
def list_clients():
    data = load_data('data.json')
    clients = {user_id: user_data for user_id, user_data in data.items() if user_data.get('type') == 'client'}
    return clients


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
    data = load_data('data.json')
    num = 0
    for user_id, user_data in data.items():
        if user_data.get('type') == 'client':
            orders = user_data.get('orders', [])
            num += len(orders)
    return num


def get_max_order_id():
    data = load_data('data.json')
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


def migrate_data():
    data = load_data('data.json')
    for user_id, user_data in data.items():
        if 'saved_name' not in user_data:
            user_data['saved_name'] = ''
        if 'debt' not in user_data:
            user_data['debt'] = 0
        if 'orders' not in user_data:
            user_data['orders'] = []
        if user_data['orders']:
            for order in user_data['orders']:
                if 'is_confirmed' not in order:
                    order['is_confirmed'] = False
    save_data('data.json', data)


# Admin selects a client to edit
@bot.message_handler(func=lambda message: message.text == "/edit_client" or message.text == "Mijoz ma'lumotlarini o'zgartirish")
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
                markup.add(KeyboardButton(f"{client_data['first_name']} {client_data['last_name']} ({client_id})"))
            markup.add(KeyboardButton("Bosh menyu"))

            user_states[user_id] = 'selecting_client_for_edit'
            bot.send_message(message.chat.id, "O'zgartirish uchun mijozni tanlang:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Bunday mijoz topilmadi.")
    else:
        bot.send_message(message.chat.id, "Sizda mijozlarni o'zgartirishga ruxsat yo`q.")


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
        data = load_data('data.json')
        client_data = data.get(selected_client_id, {})
        client_info = (
            f"Mijoz haqida:\n"
            f"Username: {client_data.get('username', 'Not set')}\n"
            f"Ism: {client_data.get('first_name')}\n"
            f"Familiya: {client_data.get('last_name')}\n"
            f"Sistemadagi Ism: {client_data.get('saved_name')}\n"
            f"Qarzi: {client_data.get('debt')}\n"
            f"Type: {client_data.get('type')}\n"
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
        bot.send_message(message.chat.id, f"Siz haqiqatan ham mijozni o'chirishni xohlaysizmi? ({selected_client_id})", reply_markup=markup)
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


# Function to check if user exists
def user_exists(user_id):
    data = load_data('data.json')
    return user_id in data


# Handle client deletion confirmation
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'confirming_client_deletion')
@user_command_wrapper
def handle_confirm_client_deletion(message):
    user_id = str(message.from_user.id)
    confirmation = message.text.strip()

    if confirmation == "Ha":
        # Proceed to delete the client
        selected_client_id = admin_selected_clients.get(user_id)
        data = load_data('data.json')

        if selected_client_id in data:
            # Send a message to the deleted user
            try:
                bot.send_message(selected_client_id, "Sizning profilingiz o'chirildi. Bottan foydalanish uchun /start ni kiriting.")
            except Exception as e:
                print(f"Could not send message to deleted user: {e}")

            del data[selected_client_id]
            save_data('data.json', data)
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
        data = load_data('data.json')
        client_data = data.get(selected_client_id, {})

        # Update the correct field based on the state
        state = user_states[user_id]
        if state == 'editing_username':
            client_data['username'] = new_value
            bot.send_message(message.chat.id, f"Username o`zgartirildi '{new_value}'.")
            back_to_menu(message)
        elif state == 'editing_ism':
            client_data['first_name'] = new_value
            bot.send_message(message.chat.id, f"Ism o`zgartirildi '{new_value}'.")
            back_to_menu(message)
        elif state == 'editing_familiya':
            client_data['last_name'] = new_value
            bot.send_message(message.chat.id, f"Familiya o`zgartirildi '{new_value}'.")
            back_to_menu(message)
        elif state == 'editing_sistemadagi_ism':
            client_data['saved_name'] = new_value
            bot.send_message(message.chat.id, f"Sistemadagi ism o`zgartirildi '{new_value}'.")
            back_to_menu(message)
        elif state == 'editing_qarzi':
            try:
                client_data['debt'] = int(new_value)
                bot.send_message(message.chat.id, f"Qarz o`zgartirildi {new_value}.")
                back_to_menu(message)
            except ValueError:
                bot.send_message(message.chat.id, "Qarzni noto`g`ri kiritdingiz. Iltimos, qaytadan kiriting.")
                back_to_menu(message)
        elif state == 'editing_type':
            if new_value in ['Admin', 'Client']:
                client_data['type'] = new_value.lower()  # Store as 'admin' or 'client'
                bot.send_message(message.chat.id, f"User type o`zgartirildi '{new_value.lower()}'.")
                back_to_menu(message)
            else:
                bot.send_message(message.chat.id, "Typeni noto`g`ri kiritdingiz. Iltimos, qaytadan kiriting.")
                back_to_menu(message)

        # Save the updated data
        data[selected_client_id] = client_data
        save_data('data.json', data)

        # Reset state
        user_states[user_id] = None
        admin_selected_clients[user_id] = None

    else:
        bot.send_message(message.chat.id, "Mijoz tanlanmangan. Iltimos, qaytadan urinib ko`ring.")


# Функция, которая выполняется при команде /start
@bot.message_handler(commands=['start'])
def start(message):
    data = load_data('data.json')
    migrate_data()
    user_id = str(message.from_user.id)

    if str(user_id) not in data:
        data[user_id] = {
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name,
            'type': 'client',  # default
            'saved_name': '',
            'debt': 0,
            'orders': []
        }
        save_data('data.json', data)
        bot.send_message(message.chat.id, f"Salom, {message.from_user.first_name}! Sizning ma`lumotlarinigiz saqlandi.")
    else:
        # Ensure the 'orders' key exists for existing users
        # if 'orders' not in data[user_id]:
        #     data[user_id]['orders'] = []
        #     save_data('data.json', data)
        bot.send_message(message.chat.id, f"Qaytadan salom, {message.from_user.first_name}!")
    back_to_menu(message)


# Function to parse user input and create an order
def parse_order_input(message_text):
    lines = message_text.strip().split("\n")

    # Extract saved name, debt, and order date from the first line
    first_line = lines[0].split("  ")
    saved_name = first_line[0]

    debt = int("".join(((lines[-2].split("  "))[-1]).split()[:-1]))
    order_date = first_line[-1]


    # Skip header line "Наименование товара  Цена  Количество(кб)  Оплата  Перечисление  Остаток долга"
    product_lines = lines[2:-2]

    products = []

    for line in product_lines:
        parts = line.split("  ")
        if len(parts) < 3:
            continue  # Skip lines that don't have enough information

        product_name = parts[0]
        price_str = "".join(parts[1].split()[:-1])
        product_price = int(price_str) if price_str else ""

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
    total_sum = int("".join(second_last[1].split()[:-1]))
    total_quantity = int(summary_line[2])
    total_debt = int("".join(summary_line[-1].split()[:-1]))

    return saved_name, debt, order_date, products, total_sum, total_quantity, total_debt


# Function to add an order from parsed input
def add_order(user_id, saved_name, debt, order_date, products, total_sum, total_quantity, total_debt):
    data = load_data('data.json')
    user_data = data.get(user_id, None)

    if user_data:
        orders = user_data.get('orders', [])
        order_id = str(get_max_order_id() + 1)  # Generate a new order ID
        print(order_id)
        order = {
            'order_id': order_id,
            'saved_name': saved_name,
            'debt': debt,
            'order_date': order_date,
            'products': products,
            'total_sum': total_sum,
            'total_quantity': total_quantity,
            'total_debt': total_debt,
            'is_confirmed': False
        }
        orders.append(order)
        user_data['orders'] = orders

        # Update the user's debt by adding the total_debt of the new order
        # user_data['debt'] += debt
        user_data['total_debt'] = debt
        print(debt, "total_debt")
        print(user_data['total_debt'])
        # Здесь нужно поменять и сделать user_data['debt'] += total_sum 
        # Тогда к исходному долгу одного юзера будет прибовляться сумма заказа

        # Save updated user data
        data[user_id] = user_data
        save_data('data.json', data)


# Function to delete an order by ID
def delete_order(user_id, order_id):
    data = load_data('data.json')
    user_data = data.get(user_id, None)

    if user_data:
        orders = user_data.get('orders', [])
        new_orders = [order for order in orders if order['order_id'] != order_id]

        if len(orders) == len(new_orders):
            return False  # Order ID not found

        user_data['orders'] = new_orders
        save_data('data.json', data)
        return True

    return False  # User ID not found


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
    data = load_data('data.json')
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
            return print_orders(orders)
        else:
            return "Buyurtma topilmadi."
    return "Mijoz topilmadi."


def get_debt(user_id):
    data = load_data('data.json')
    user_data = data.get(user_id, None)
    if user_data:
        return user_data.get('total_debt', 0)
    return 0


# Function to list all products in a specific order
def list_products(user_id, order_id):
    data = load_data('data.json')
    user_data = data.get(user_id, None)

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
                markup.add(KeyboardButton(f"{client_data['first_name']} {client_data['last_name']} ({client_id})"))
            markup.add(KeyboardButton("Bosh menyu"))

            user_states[user_id] = 'selecting_client'
            bot.send_message(message.chat.id, "Mijozni tanlang:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Mijozlar topilmadi.")
    else:
        bot.send_message(message.chat.id, "Sizda buyurtma qo`shishga ruxsat yo`q.")


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

    if client_choice == "Yangi mijoz yaratish":
        user_states[user_id] = 'creating_client'
        bot.send_message(message.chat.id,
                         "Iltimos, yangi mijozni kiritish uchun ism va familiyani yozing. Masalan: John Doe")
    else:
        # Extract client ID from the selected text (the ID is in parentheses)
        try:
            selected_client_id = client_choice.split('(')[-1].strip(')')
            admin_selected_clients[user_id] = selected_client_id
            user_states[user_id] = 'awaiting_order_data'
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Bosh menyu"))
            bot.send_message(message.chat.id, "Buyurtma ma'lumotlarini berilgan formatda kiriting:",
                             reply_markup=markup)
        except:
            bot.send_message(message.chat.id, "Noto`g`ri mijoz tanlandi. Iltimos, qaytadan urinib ko`ring.")


# Step 3: Handle the creation of a new client
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'creating_client')
@user_command_wrapper
def handle_create_client(message):
    if message.text == "Bosh menyu":
        back_to_menu(message)
        return

    if message.text in commands_list:
        redirect_to_command(message)
        return

    user_id = str(message.from_user.id)
    client_info = message.text.strip().split()

    if len(client_info) >= 2:
        first_name, last_name = client_info[0], client_info[1]

        data = load_data('data.json')
        new_client_id = str(max([int(uid) for uid in data.keys()] + [0]) + 1)  # Generate new client ID
        data[new_client_id] = {
            'username': '',  # New clients won't have usernames
            'first_name': first_name,
            'last_name': last_name,
            'type': 'client',
            'saved_name': '',
            'debt': 0,
            'orders': []
        }
        save_data('data.json', data)

        admin_selected_clients[user_id] = new_client_id  # Set this as the selected client for order
        user_states[user_id] = 'awaiting_order_data'
        bot.send_message(message.chat.id,
                         f"Yangi mijoz '{first_name} {last_name}' muvaffaqiyatli yaratildi. Endi buyurtma "
                         f"ma'lumotlarini kiriting.")
    else:
        bot.send_message(message.chat.id, "Iltimos, ism va familiyani yozing. Masalan: John Doe")


# Step 4: Handle the user's input data for orders
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'awaiting_order_data')
@user_command_wrapper
def receive_order_data(message):
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
        try:
            saved_name, debt, order_date, products, total_sum, total_quantity, total_debt = parse_order_input(
                user_input)
            add_order(selected_client_id, saved_name, debt, order_date, products, total_sum, total_quantity, total_debt)
            # Send notification to the client witha button to confirm the order
            buttons = types.InlineKeyboardMarkup()
            buttons.add(types.InlineKeyboardButton(text="Buyurtmani tasdiqlash",
                                                   callback_data=f"confirm_order {total_sum}"))
            buttons.add(types.InlineKeyboardButton(text="Buyurtmani bekor qilish",
                                                    callback_data=f"cancel_order {total_sum}"))
            bot.send_message(selected_client_id, f"Buyurtma muvaffaqiyatli qo`shildi. Jami summa: {total_sum} сўм",
                             reply_markup=buttons)
            user_states[selected_client_id] = ['confirming_order', message.chat.id]
            bot.send_message(message.chat.id, "Buyurtma muvaffaqiyatli qo`shildi va mijozga yetkazildi.")
            back_to_menu(message)
        except Exception as e:
            bot.send_message(message.chat.id, f"Buyurtma noto`g`ri kiritilgan {e}")
        finally:
            user_states[user_id] = None
            admin_selected_clients[user_id] = None
    else:
        bot.send_message(message.chat.id, "Mijoz tanlanmagan. Iltimos, qaytadan urinib ko`ring.")


@bot.callback_query_handler(func=lambda call: user_states.get(str(call.from_user.id))[0] == 'confirming_order')
def handle_confirm_order(call):
    user_id = str(call.from_user.id)
    user_data = load_data('data.json').get(user_id, None)
    if call.data.startswith("confirm_order"):
        total_sum = int(call.data.split()[-1])
        user_data['debt'] += total_sum
        bot.send_message(call.message.chat.id, f"Buyurtma tasdiqlandi. Qarz: {user_data['debt']} сўм")
        user_data['orders'][-1]['is_confirmed'] = True
        data = load_data('data.json')
        data[user_id] = user_data
        save_data('data.json', data)
        bot.send_message(user_states[user_id][1], f"{user_data['first_name']} {user_data['last_name']}"
                                                  f" buyurtmasi tasdiqlandi.")
        user_states[user_id] = None
        back_to_menu(call.message)
    elif call.data.startswith("cancel_order"):
        bot.send_message(call.message.chat.id, f"Buyurtma bekor qilindi. Qarz: {user_data['debt']} сўм")
        save_data('data.json', load_data('data.json'))
        bot.send_message(user_states[user_id][1], f"{user_data['first_name']} {user_data['last_name']}"
                                                  f" buyurtmasi bekor qilindi.")
        user_states[user_id] = None
        back_to_menu(call.message)


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
        admin_selected_clients[user_id] = selected_client_id

        # Show the list of orders for the selected client
        data = load_data('data.json')
        client_data = data.get(selected_client_id, {})
        orders = client_data.get('orders', [])

        if orders:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for order in orders:
                markup.add(KeyboardButton(
                    f"Buyurtma ID: {order['order_id']}, Miqdor: {order['total_sum']}, Sana: {order['order_date']}"))
            markup.add(KeyboardButton("Bosh menyu"))

            user_states[user_id] = 'selecting_order_for_deletion'
            bot.send_message(message.chat.id, "O'chirish uchun buyurtmani tanlang:", reply_markup=markup)
        else:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Bosh menyu"))
            bot.send_message(message.chat.id, "Mijozda buyurtmalar topilmadi.", reply_markup=markup)

    except Exception as e:
        bot.send_message(message.chat.id, f"Mijoz noto`g`ri tanlangan: {e}")


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
            data = load_data('data.json')
            client_data = data.get(selected_client_id, {})
            orders = client_data.get('orders', [])

            # Filter the order to be deleted
            new_orders = [order for order in orders if order['order_id'] != selected_order_id]

            if len(orders) == len(new_orders):
                bot.send_message(message.chat.id, f"Buyurtma {selected_order_id} topilmadi.")
            else:
                client_data['orders'] = new_orders
                data[selected_client_id] = client_data
                save_data('data.json', data)
                markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
                markup.add(KeyboardButton("Buyurtma qo'shish"), KeyboardButton("Buyurtmani o'chirish"))
                markup.add(KeyboardButton("Mijoz ma'lumotlarini o'zgartirish"), KeyboardButton("Buyurtmalarni ko'rish"))
                bot.send_message(message.chat.id, f"Buyurtma {selected_order_id} o`chirildi.")
                bot.send_message(message.chat.id, "Menyu", reply_markup=markup)
                print("Back to menu")

        # Reset state
        user_states[user_id] = None
        admin_selected_clients[user_id] = None

    except Exception as e:
        bot.send_message(message.chat.id, f"Buyurtmani o`chirib bo`lmadi: {e}")


# Handle the /list_orders command
@bot.message_handler(func=lambda message: message.text == "/list_orders" or message.text == "Buyurtmalarni ko'rish")
@user_command_wrapper
def handle_list_orders(message):
    user_id = str(message.from_user.id)

    if is_client(user_id):
        orders_list = list_orders(user_id)  # Clients can only list their own orders
        total_debt = get_debt(user_id)
        combined_message = f"Qarz: {':,'.format(total_debt)} сўм \n{orders_list}"
        bot.send_message(message.chat.id, combined_message)

         # If the client has orders, prompt to see products
        if "Buyurtma ID" in orders_list:
            bot.send_message(message.chat.id, "Buyurtmaning mahsulotlarini ko'rish uchun buyurtma ID ni yuboring. Masalan: /list_products 1")

    elif is_admin(user_id):
        # Admins can list all orders
        orders_list = list_orders(user_id)
        bot.send_message(message.chat.id, orders_list)

         # If there are any orders, prompt to see products
        if "Buyurtma ID" in orders_list:
            bot.send_message(message.chat.id, "Buyurtmaning mahsulotlarini ko'rish uchun buyurtma ID ni yuboring. Masalan: /list_products 1")

    else:
        bot.send_message(message.chat.id, "Sizda buyurtmalar ro`yxati ko`rishga ruxsat yo`q.")
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

    # Search for the order by ID across all users if the requester is an admin
    if is_admin(user_id):
        data = load_data('data.json')
        for client_id, client_data in data.items():
            orders = client_data.get('orders', [])
            for order in orders:
                if order['order_id'] == order_id:
                    # Filter products with quantity greater than 0
                    products = [product for product in order['products'] if product['product_quantity'] > 0]
                    products_list = "\n".join([
                        f"Mahsulot: {product['product_name']}, Narx: {product['product_price']}, "
                        f"Miqdori: {product['product_quantity']}"
                        for product in products
                    ])
                    if not products_list:
                        products_list = "Mahsulotlar topilmadi."
                    bot.send_message(message.chat.id, products_list)
                    return
        # If no order found
        bot.send_message(message.chat.id, f"Buyurtma ID {order_id} topilmadi.")
    elif is_client(user_id):
        # Clients can only list their own products
        products_list = list_products(user_id, order_id)
        bot.send_message(message.chat.id, products_list)
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
