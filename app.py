from flask import Flask, request, jsonify
import random

app = Flask(__name__)

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

def generate_card(bin_template):
    while True:
        card = ''.join(str(random.randint(0, 9)) if ch == 'x' else ch for ch in bin_template)
        if luhn(card):
            return card

def detect_card_type(number):
    if number.startswith('4'):
        return 'visa'
    elif number.startswith(('51', '52', '53', '54', '55')):
        return 'mastercard'
    elif number.startswith(('34', '37')):
        return 'amex'
    elif number.startswith(('6011', '622', '64', '65')):
        return 'discover'
    else:
        return 'unknown'

@app.route('/api/ccgenerator', methods=['GET'])
def cc_generator():
    bin_input = request.args.get('bin')
    count = int(request.args.get('count', 1))

    if not bin_input or 'x' not in bin_input:
        return jsonify({'error': 'Invalid BIN format'}), 400

    try:
        parts = bin_input.split('|')
        bin_template = parts[0]
        exp_month = parts[1] if len(parts) > 1 else str(random.randint(1, 12)).zfill(2)
        exp_year = parts[2] if len(parts) > 2 else str(random.randint(2025, 2030))
        cvv = parts[3] if len(parts) > 3 else str(random.randint(0, 999)).zfill(3)
    except Exception:
        return jsonify({'error': 'Error parsing BIN input'}), 400

    cards = []
    for _ in range(count):
        card_number = generate_card(bin_template)
        card_type = detect_card_type(card_number)
        cards.append({
            'card': f'{card_number}|{exp_month}|{exp_year}|{cvv}',
            'card_type': card_type
        })

    return jsonify({
        'count': count,
        'generated': cards,
        'input': bin_input
    })

if __name__ == '__main__':
    app.run(debug=True)
