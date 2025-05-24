from flask import Flask, request, jsonify
import random

app = Flask(__name__)

# --------- Core Utils ----------

def luhn_checksum(card_number):
    def digits_of(n): return [int(d) for d in str(n)]
    digits = digits_of(card_number)
    odd = digits[-1::-2]
    even = digits[-2::-2]
    total = sum(odd)
    for d in even:
        total += sum(digits_of(d * 2))
    return total % 10

def complete_luhn(prefix, total_length):
    number = prefix
    while len(number) < (total_length - 1):
        number += str(random.randint(0, 9))
    check_digit = (10 - luhn_checksum(int(number) * 10)) % 10
    return number + str(check_digit)

def detect_card_type(card_number):
    if card_number.startswith('4'):
        return 'visa'
    elif 51 <= int(card_number[:2]) <= 55 or 2221 <= int(card_number[:4]) <= 2720:
        return 'mastercard'
    elif 50 <= int(card_number[:2]) <= 69:
        return 'maestro'
    else:
        return 'unknown'

# --------- API Route ----------

@app.route('/api/ccgenerator', methods=['GET'])
def cc_generator():
    bin_input = request.args.get('bin')
    count = int(request.args.get('count', 1))

    if not bin_input:
        return jsonify({'error': 'Missing BIN input'}), 400

    results = []

    try:
        parts = bin_input.split('|')
        number_part = parts[0].replace('x', '')
        masked_len = len(parts[0])
        exp_month = parts[1] if len(parts) > 1 else f"{random.randint(1, 12):02d}"
        exp_year = parts[2] if len(parts) > 2 else str(random.randint(2025, 2030))
        cvv = parts[3] if len(parts) > 3 else None

        for _ in range(count):
            card_number = complete_luhn(number_part, masked_len)
            full_cvv = cvv if cvv else f"{random.randint(100, 999)}"
            results.append({
                "card": f"{card_number}|{exp_month}|{exp_year}|{full_cvv}",
                "card_type": detect_card_type(card_number)
            })

        return jsonify({
            "input": bin_input,
            "generated": results,
            "count": len(results)
        })

    except Exception as e:
        return jsonify({'error': 'Invalid input format', 'details': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
