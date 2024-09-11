import json
import telebot
from telebot.types import BotCommand, ReplyKeyboardMarkup, KeyboardButton

TOKEN = '7099572080:AAH6FYY_KDVrCgvhVa8CgV2ZdTIESi0JZEw'

bot = telebot.TeleBot(TOKEN)

# Dictionary to keep track of which users are expected to provide data
user_states = {}
admin_selected_clients = {}  # To keep track of the client selected by the admin for adding an order


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


# Admin selects a client to edit
@bot.message_handler(commands=['edit_client'])
def handle_edit_client(message):
    user_id = str(message.from_user.id)

    if is_admin(user_id):
        clients = list_clients()

        if clients:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for client_id, client_data in clients.items():
                markup.add(KeyboardButton(f"{client_data['first_name']} {client_data['last_name']} ({client_id})"))

            user_states[user_id] = 'selecting_client_for_edit'
            bot.send_message(message.chat.id, "O'zgartirish uchun mijozni tanlang:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Bunday mijoz topilmadi.")
    else:
        bot.send_message(message.chat.id, "Sizda mijozlarni o'zgartirishga ruxsat yo`q.")


# Handle the selection of a client for editing
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_client_for_edit')
def handle_select_client_for_edit(message):
    user_id = str(message.from_user.id)
    client_choice = message.text.strip()

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
        markup.add(KeyboardButton("Username"), KeyboardButton("Ism"), KeyboardButton("Famailya"))
        markup.add(KeyboardButton("Sistemadagi Ism"), KeyboardButton("Qarzi"), KeyboardButton("Type"))
        user_states[user_id] = 'choosing_field_to_edit'
        bot.send_message(message.chat.id, "Qaysi maydonni o'zgartirish?", reply_markup=markup)

    except Exception as e:
        bot.send_message(message.chat.id, f"Noto`g'ri mijoz tanlandi: {e}")


# Handle field selection for editing
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'choosing_field_to_edit')
def handle_choose_field_to_edit(message):
    user_id = str(message.from_user.id)
    field_choice = message.text.strip()

    if field_choice in ["Username", "Ism", "Familiya", "Sistemadagi Ism", "Qarzi", "Type"]:
        # Special handling for 'Type' to show buttons
        if field_choice == "Type":
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("Admin"), KeyboardButton("Client"))
            user_states[user_id] = 'editing_type'
            bot.send_message(message.chat.id, "Mijoz typeni tanlang:", reply_markup=markup)
        else:
            user_states[user_id] = f"editing_{field_choice.lower().replace(' ', '_')}"
            bot.send_message(message.chat.id, f"Yangi {field_choice.lower()} kiriting:")
    else:
        bot.send_message(message.chat.id, "Invalid choice. Please select a valid field.")


# Handle updating the selected field
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) and user_states.get(
    str(message.from_user.id)).startswith('editing'))
def handle_edit_field(message):
    user_id = str(message.from_user.id)
    selected_client_id = admin_selected_clients.get(user_id)
    new_value = message.text.strip()

    print(user_id)
    print(selected_client_id)
    print(new_value)

    if selected_client_id:
        data = load_data('data.json')
        client_data = data.get(selected_client_id, {})

        # Update the correct field based on the state
        state = user_states[user_id]
        if state == 'editing_username':
            client_data['username'] = new_value
            bot.send_message(message.chat.id, f"Username o`zgartirildi '{new_value}'.")
        elif state == 'editing_ism':
            client_data['first_name'] = new_value
            bot.send_message(message.chat.id, f"Ism o`zgartirildi '{new_value}'.")
        elif state == 'editing_familiya':
            client_data['last_name'] = new_value
            bot.send_message(message.chat.id, f"Familiya o`zgartirildi '{new_value}'.")
        elif state == 'editing_sistemadagi_ism':
            client_data['saved_name'] = new_value
            bot.send_message(message.chat.id, f"Sistemadagi ism o`zgartirildi '{new_value}'.")
        elif state == 'editing_qarzi':
            try:
                client_data['debt'] = int(new_value)
                bot.send_message(message.chat.id, f"Qarz o`zgartirildi {new_value}.")
            except ValueError:
                bot.send_message(message.chat.id, "Qarzni noto`g`ri kiritdingiz. Iltimos, qaytadan kiriting.")
        elif state == 'editing_type':
            if new_value in ['Admin', 'Client']:
                client_data['type'] = new_value.lower()  # Store as 'admin' or 'client'
                bot.send_message(message.chat.id, f"User type o`zgartirildi '{new_value.lower()}'.")
            else:
                bot.send_message(message.chat.id, "Typeni noto`g`ri kiritdingiz. Iltimos, qaytadan kiriting.")

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
        if 'orders' not in data[user_id]:
            data[user_id]['orders'] = []
            save_data('data.json', data)
        bot.send_message(message.chat.id, f"Qaytadan salom, {message.from_user.first_name}!")


# Function to parse user input and create an order
def parse_order_input(message_text):
    lines = message_text.strip().split("\n")

    # Extract saved name, debt, and order date from the first line
    first_line = lines[0].split("  ")
    saved_name = first_line[0]
    debt = int("".join((first_line[2].split())[:-1]))
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
    total_sum = int("".join(summary_line[1].split()[:-1]))
    total_quantity = int(summary_line[2])
    total_debt = int("".join(summary_line[-1].split()[:-1]))

    return saved_name, debt, order_date, products, total_sum, total_quantity, total_debt


# Function to add an order from parsed input
def add_order(user_id, saved_name, debt, order_date, products, total_sum, total_quantity, total_debt):
    data = load_data('data.json')
    user_data = data.get(user_id, None)

    if user_data:
        orders = user_data.get('orders', [])
        order_id = str(len(orders) + 1)
        order = {
            'order_id': order_id,
            'saved_name': saved_name,
            'debt': debt,
            'order_date': order_date,
            'products': products,
            'total_sum': total_sum,
            'total_quantity': total_quantity,
            'total_debt': total_debt
        }
        orders.append(order)
        user_data['orders'] = orders  # Update the user data with the new order list
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


# Function to list all orders for a user
def list_orders(user_id):
    data = load_data('data.json')
    user_data = data.get(user_id, None)

    if user_data:
        orders = user_data.get('orders', [])
        if orders:
            return "\n".join(
                [f"Buyurtma ID: {order['order_id']}, miqdor: {order['total_sum']}, sana: {order['order_date']}" for
                 order in orders])
        else:
            return "Buyurtma topilmadi."
    return "Mijoz topilmadi."


# Function to list all products in a specific order
def list_products(user_id, order_id):
    data = load_data('data.json')
    user_data = data.get(user_id, None)

    if user_data:
        orders = user_data.get('orders', [])
        for order in orders:
            if order['order_id'] == order_id:
                products = order.get('products', [])
                if products:
                    return "\n".join([
                                         f"Mahsulot: {product['product_name']}, Narx: {product['product_price']}, "
                                         f"Miqdori: {product['product_quantity']}"
                                         for product in products])
                else:
                    return "Mahsulot topilmadi."
        return "Buyurtma topilmadi."
    return "Mijoz topilmadi."


# Example function to add a product
def add_product(product_name, product_price, product_quantity):
    return {
        'product_name': product_name,
        'product_price': product_price,
        'product_quantity': product_quantity
    }


# Step 1: Handle the /add_order command
@bot.message_handler(commands=['add_order'])
def handle_add_order(message):
    user_id = str(message.from_user.id)

    if is_admin(user_id):
        clients = list_clients()

        if clients:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for client_id, client_data in clients.items():
                markup.add(KeyboardButton(f"{client_data['first_name']} {client_data['last_name']} ({client_id})"))
            markup.add(KeyboardButton("Yangi mijoz yaratish"))

            user_states[user_id] = 'selecting_client'
            bot.send_message(message.chat.id, "Mijozni tanlang yoki yangisini yarating:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Mijozlar topilmadi. Iltimos, yangi mijoz yarating.")
    else:
        bot.send_message(message.chat.id, "Sizda buyurtma qo`shishga ruxsat yo`q.")


# Step 2: Handle the selection of a client or creating a new client
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_client')
def handle_select_client(message):
    user_id = str(message.from_user.id)
    client_choice = message.text.strip()

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
            bot.send_message(message.chat.id, "Buyurtma ma'lumotlarini berilgan formatda kiriting:")
        except:
            bot.send_message(message.chat.id, "Noto`g`ri mijoz tanlandi. Iltimos, qaytadan urinib ko`ring.")


# Step 3: Handle the creation of a new client
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'creating_client')
def handle_create_client(message):
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
def receive_order_data(message):
    user_id = str(message.from_user.id)
    user_input = message.text.strip()
    selected_client_id = admin_selected_clients.get(user_id)

    if selected_client_id:
        try:
            saved_name, debt, order_date, products, total_sum, total_quantity, total_debt = parse_order_input(
                user_input)
            add_order(selected_client_id, saved_name, debt, order_date, products, total_sum, total_quantity, total_debt)
            bot.send_message(message.chat.id, "Buyurtma muvaffaqiyatli qo`shildi.")
        except Exception as e:
            bot.send_message(message.chat.id, f"Buyurtma noto`g`ri kiritilgan {e}")
        finally:
            user_states[user_id] = None
            admin_selected_clients[user_id] = None
    else:
        bot.send_message(message.chat.id, "Mijoz tanlanmagan. Iltimos, qaytadan urinib ko`ring.")


# Example of using delete_order function
@bot.message_handler(commands=['delete_order'])
def handle_delete_order(message):
    user_id = str(message.from_user.id)

    if is_admin(user_id):
        clients = list_clients()

        if clients:
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for client_id, client_data in clients.items():
                markup.add(KeyboardButton(f"{client_data['first_name']} {client_data['last_name']} ({client_id})"))

            user_states[user_id] = 'selecting_client_for_order_deletion'
            bot.send_message(message.chat.id, "Mijoqni tanlang", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Bunday mijozlar topilmadi.")
    else:
        bot.send_message(message.chat.id, "Sizda buyurtmani o`chirishga ruxsat yo`q.")


# Handle the selection of a client for deleting an order
@bot.message_handler(
    func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_client_for_order_deletion')
def handle_select_client_for_order_deletion(message):
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

            user_states[user_id] = 'selecting_order_for_deletion'
            bot.send_message(message.chat.id, "O'chirish uchun buyurtmani tanlang:", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Mijozda buyurtmalar topilmadi.")

    except Exception as e:
        bot.send_message(message.chat.id, f"Mijoz noto`g`ri tanlangan: {e}")


# Handle the selection of an order to delete
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id)) == 'selecting_order_for_deletion')
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
                bot.send_message(message.chat.id, f"Buyurtma {selected_order_id} o`chirish.")

        # Reset state
        user_states[user_id] = None
        admin_selected_clients[user_id] = None

    except Exception as e:
        bot.send_message(message.chat.id, f"Buyurtmani o`chirib bo`lmadi: {e}")


# Handle the /list_orders command
@bot.message_handler(commands=['list_orders'])
def handle_list_orders(message):
    user_id = str(message.from_user.id)

    if is_client(user_id):
        orders_list = list_orders(user_id)  # Clients can only list their own orders
        bot.send_message(message.chat.id, orders_list)
    elif is_admin(user_id):
        # Admins can list all orders
        orders_list = list_orders(user_id)
        bot.send_message(message.chat.id, orders_list)
    else:
        bot.send_message(message.chat.id, "Sizda buyurtmalar ro`yxati ko`rishga ruxsat yo`q.")


# Handle the /list_products command
@bot.message_handler(commands=['list_products'])
def handle_list_products(message):
    user_id = str(message.from_user.id)
    command_parts = message.text.split()

    if len(command_parts) < 2:
        bot.send_message(message.chat.id, "Buyurtma ID ni kiritish kerak. Masalan: /list_products 1")
        return

    order_id = command_parts[1]  # Extract order ID from the message
    products_list = list_products(user_id, order_id)
    bot.send_message(message.chat.id, products_list)


@bot.message_handler(commands=['help'])
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
