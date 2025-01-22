import csv
from twilio.rest import Client
import master_file

# Twilio configuration
account_sid = master_file.account_SID
auth_token = master_file.auth_token
client = Client(account_sid, auth_token)
twilio_phone_number = '+18445801151'



def send_message(from_number, to_number, message):
    """
    Sends a message using Twilio.
    """
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
    """
    Cleans and formats phone numbers to +1XXXXXXXXXX format.
    """
    phone = phone.replace('-', '').replace(' ', '')
    if not phone.startswith('+1') and len(phone) != 0:
        phone = '+1' + phone
    return phone[:12]


# Path to the input and output CSV files
input_file_path = 'fake_numbers.csv'
output_file_path = 'Sent Numbers.csv'

# Load sent numbers from the persistent file
sent_numbers = set()
try:
    with open(output_file_path, 'r', newline='') as sent_file:
        csv_reader = csv.reader(sent_file)
        next(csv_reader)  # Skip the header row
        for row in csv_reader:
            if len(row) >= 2:  # Ensure valid rows
                sent_numbers.add(row[1])  # Add the phone number to the set
except FileNotFoundError:
    print(f"No existing sent numbers file found. A new one will be created.")
except Exception as e:
    print(f"Error loading sent numbers: {e}")


# Process the input file and update the sent numbers
try:
    with open(input_file_path, 'r', newline='') as names_file, \
         open(output_file_path, 'a', newline='') as sent_file:  # Append mode for sent file

        csv_reader = csv.reader(names_file)
        csv_writer = csv.writer(sent_file)

        # Write header to the output file if it's newly created
        if sent_file.tell() == 0:  # Check if the file is empty
            csv_writer.writerow(["Name", "Phone Number"])

        next(csv_reader)  # Skip the header row
        i = 1

        for row in csv_reader:
            try:
                # Ensure the row has enough fields
                if len(row) < 5:
                    print(f"Skipping incomplete row {i}: {row}")
                    i += 1
                    continue

                # Extract values from the row
                title, name, phone, email, business = row[:5]
                phone = clean_phone_number(phone)

                # Prepare the message
                message = (
                    "We’re running promotions on intercom upgrades to modernize your properties. "
                    "It takes zero effort to get a quote—we can send someone out to check the property, "
                    "even if you’re not present. Just text me a few addresses you’re considering upgrading, "
                    "and we’ll handle the rest. \n\nWe’ve worked with many multi-family property owners, "
                    "and they’ve been thrilled with the results. Check out the reviews: https://g.co/kgs/U1UtBKH. "
                    "\n\nLet’s make this easy—text me to get started!"
                )

                # Send the message if the phone number is valid and not already sent
                if len(phone) != 0 and phone not in sent_numbers:
                    send_message(twilio_phone_number, phone, message)
                    csv_writer.writerow([name, phone])  # Add to the persistent file
                    sent_numbers.add(phone)  # Update the in-memory set
                    print(f"{i}. Sending text to {phone}")
                else:
                    print(f"{i}. Duplicate or invalid phone number for {name}. Skipping.")

                i += 1

            except Exception as e:
                print(f"Error processing row {i}: {row}. Error: {e}")
                i += 1

except FileNotFoundError:
    print(f"Error: Input file not found at {input_file_path}")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
