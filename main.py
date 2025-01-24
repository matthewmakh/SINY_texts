import csv
from twilio.rest import Client
import master_file
from datetime import datetime

# Twilio configuration
account_sid = master_file.account_SID
auth_token = master_file.auth_token
client = Client(account_sid, auth_token)
twilio_phone_number = '+18445801151'
now = datetime.now()
current_time = now.strftime("%Y-%m-%d %H:%M")



def send_message(from_number, to_number, message):
    try:
        client.messages.create(
            from_=from_number,
            body=message,
            to=to_number
        )
        print(f"Message sent successfully to {to_number}")
    except Exception as e:
        print(f"Failed to send message to {to_number}: {e}")


def clean_phone_number(phone):
    phone = phone.replace('-', '').replace(' ', '')
    if not phone.startswith('+1') and len(phone) != 0:
        phone = '+1' + phone
    return phone[:12]


#file with names and phone numbers
input_file_path = 'Numbers_to_send'

#file of all the numbers that were already texted. this is used to make sue that we dont multitext people.
#it also keeps a log of the day and time that the text burst went out
output_file_path = 'Sent_numbers.csv'


#creates a new set that is then looked into later to ensure that we dont double send a text.
#every time this is run the sent numbers set is loaded up with every phone number in Sent_numbers.csv
sent_numbers = set()
try:
    with open(output_file_path, 'r', newline='') as sent_file:
        csv_reader = csv.reader(sent_file)
        next(csv_reader)
        for row in csv_reader:
            if len(row) >= 2:
                sent_numbers.add(row[1])
except FileNotFoundError:
    print(f"No existing sent numbers file found. A new one will be created.")
except Exception as e:
    print(f"Error loading sent numbers: {e}")



try:
    with open(input_file_path, 'r', newline='') as names_file, \
         open(output_file_path, 'a', newline='') as sent_file:

        csv_reader = csv.reader(names_file)
        csv_writer = csv.writer(sent_file)
        # Add a date header and empty rows if the file is not empty
        if sent_file.tell() > 0:
            csv_writer.writerow([])  # Empty row
            csv_writer.writerow([])  # Empty row
            csv_writer.writerow([])  # Empty row

        # Add a date header
        today_date = datetime.now().strftime("%B %d, %Y %I:%M %p")
        csv_writer.writerow([f"Sent on: {today_date}"])
        csv_writer.writerow([])  # Empty row
        csv_writer.writerow([])  # Empty row


        #if the first trow is empty we fill it with the header of the csv
        if sent_file.tell() == 0:
            csv_writer.writerow(["Name", "Phone Number"])

        #skips the first row of the csv when reading
        next(csv_reader)
        i = 1
        #this keeps track of the number of texts you sent so that you dont spam
        count = 0

        for row in csv_reader:

            if count <= 300:
                try:

                    if len(row) < 5:
                        print(f"Skipping incomplete row {i}: {row}")
                        i += 1
                        continue


                    title, name, phone, email, business = row[:5]
                    phone = clean_phone_number(phone)


                    #this is the actual text we send
                    message = (
                        "We’re running promotions on intercom upgrades to modernize your properties. "
                        "It takes zero effort to get a quote—we can send someone out to check the property, "
                        "even if you’re not present. Just text me a few addresses you’re considering upgrading, "
                        "and we’ll handle the rest. \n\nWe’ve worked with many multi-family property owners, "
                        "and they’ve been thrilled with the results. Check out the reviews: https://g.co/kgs/U1UtBKH. "
                        "\n\nLet’s make this easy—text me to get started!"
                    )


                    #here we make sure that a phone number exists and we didnt already send them a text.
                    if len(phone) != 0 and phone not in sent_numbers:
                        #send_message(twilio_phone_number, phone, message)

                        #we write the sent text number to the sent numbers csv
                        csv_writer.writerow([name, phone])
                        sent_numbers.add(phone)
                        print(f"{i}. Sending text to {phone}")
                        count += 1
                    else:
                        print(f"{i}. Duplicate or invalid phone number for {name}. Skipping.")
                        csv_writer.writerow([f"Duplicate or invalid phone number for {name}: {phone}. Skipping."])

                    i += 1


                except Exception as e:
                    print(f"Error processing row {i}: {row}. Error: {e}")
                    i += 1
                    count += 1

except FileNotFoundError:
    print(f"Error: Input file not found at {input_file_path}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")



