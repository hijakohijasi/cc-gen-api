from flask import Flask, request, jsonify
import random

app = Flask(__name__)

CARD_LENGTHS = {
    'visa': 16,
    'mastercard': 16,
    'amex': 15,
    'discover': 16
}

def luhn(card_number):
    total = 0
    reverse_digits = card_number[::-1]
    for i, digit in enumerate(reverse_digits):
        n = int(digit)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0

def detect_card_type(number):
    if number.startswith('4'):
        return 'visa'
    elif number.startswith(('51', '52', '53', '54', '55')):
        return 'mastercard'
    elif number.startswith(('34', '37')):
        return 'amex'
    elif number.startswith(('6011', '622', '64', '65')):
        return 'discover'
    return 'unknown'

def generate_card_number(partial_bin, length):
    x_count = length - len(partial_bin)
    while True:
        random_part = ''.join(random.choice('0123456789') for _ in range(x_count))
        card_number = partial_bin + random_part
        if luhn(card_number):
            return card_number

@app.route('/api/ccgenerator', methods=['GET'])
def cc_generator():
    bin_input = request.args.get('bin', '')
    count = int(request.args.get('count', 1))

    try:
        parts = bin_input.split('|')
        raw_bin = parts[0]
        exp_month = parts[1] if len(parts) > 1 else str(random.randint(1, 12)).zfill(2)
        exp_year = parts[2] if len(parts) > 2 else str(random.randint(2025, 2030))
        cvv = parts[3] if len(parts) > 3 else str(random.randint(0, 999)).zfill(3)
    except Exception:
        return jsonify({'error': 'Error parsing BIN input'}), 400

    # Remove x from BIN
    partial_bin = raw_bin.replace('x', '')

    # Detect card type
    card_type = detect_card_type(partial_bin)
    card_length = CARD_LENGTHS.get(card_type, 16)  # Default to 16 if unknown

    generated_cards = []
    for _ in range(count):
        card_number = generate_card_number(partial_bin, card_length)
        detected_type = detect_card_type(card_number)
        generated_cards.append({
            'card': f'{card_number}|{exp_month}|{exp_year}|{cvv}',
            'card_type': detected_type
        })

    return jsonify({
        'input': bin_input,
        'count': count,
        'generated': generated_cards
    })

if __name__ == '__main__':
    app.run(debug=True)
