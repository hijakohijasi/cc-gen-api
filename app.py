from flask import Flask, request, jsonify, abort, g
import random
import re
import logging
import requests
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
CARD_LENGTHS = {
    'visa': [13, 16],
    'mastercard': 16,
    'amex': 15,
    'discover': 16,
    'jcb': 16,
    'diners': 14,
    'maestro': [12, 13, 14, 15, 16, 17, 18, 19],
    'unionpay': [16, 17, 18, 19]
}

CARD_PREFIXES = {
    'visa': ['4'],
    'mastercard': ['51', '52', '53', '54', '55', '2221', '2222', '2223', '2224', '2225', 
                  '2226', '2227', '2228', '2229', '223', '224', '225', '226', '227', '228', 
                  '229', '23', '24', '25', '26', '270', '271', '2720'],
    'amex': ['34', '37'],
    'discover': ['6011', '644', '645', '646', '647', '648', '649', '65'],
    'jcb': ['3528', '3529', '353', '354', '355', '356', '357', '358'],
    'diners': ['300', '301', '302', '303', '304', '305', '36', '38', '39'],
    'maestro': ['5018', '5020', '5038', '5893', '6304', '6759', '6761', '6762', '6763'],
    'unionpay': ['62', '81']
}

def validate_bin_format(bin_input):
    return bool(re.match(r'^(\d+x*)(\|\d{2})?(\|\d{2,4})?(\|\d{3,4})?$', bin_input))

def detect_card_type(number):
    for card_type, prefixes in CARD_PREFIXES.items():
        for prefix in prefixes:
            if number.startswith(prefix):
                return card_type
    return 'unknown'

def get_card_length(card_type):
    length = CARD_LENGTHS.get(card_type, 16)
    return random.choice(length) if isinstance(length, list) else length

def luhn_checksum(card_number):
    def digits_of(n): return [int(d) for d in str(n)]
    digits = digits_of(card_number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d * 2))
    return checksum % 10

def calculate_luhn(partial_number):
    checksum = luhn_checksum(partial_number + '0')
    return (10 - checksum) % 10

def generate_card_number(partial_bin, length):
    partial_bin = partial_bin[:length-1]
    needed_digits = length - len(partial_bin) - 1
    if needed_digits < 0:
        raise ValueError("BIN is too long for the card type")
    middle_digits = ''.join(random.choice('0123456789') for _ in range(needed_digits))
    check_digit = str(calculate_luhn(partial_bin + middle_digits))
    return partial_bin + middle_digits + check_digit

def generate_cvv(card_type):
    return str(random.randint(1000, 9999)) if card_type == 'amex' else str(random.randint(100, 999)).zfill(3)

def parse_bin_input(bin_input):
    parts = bin_input.split('|')
    raw_bin = parts[0]
    exp_month = parts[1] if len(parts) > 1 else f"{random.randint(1, 12):02d}"
    if len(parts) > 2:
        exp_year = parts[2]
        if len(exp_year) == 2:
            century = datetime.now().year // 100
            exp_year = f"{century}{exp_year}"
    else:
        exp_year = str(random.randint(datetime.now().year, datetime.now().year + 8))
    if len(parts) > 3:
        cvv = parts[3].zfill(3)[:4]
    else:
        cvv = None
    return raw_bin, exp_month, exp_year, cvv

def lookup_bin_info(bin_prefix):
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin_prefix}", headers={"Accept-Version": "3"})
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        logger.warning(f"BIN lookup failed: {e}")
        return None

def get_bin_metadata(bin_prefix):
    bin_info = lookup_bin_info(bin_prefix)
    if not bin_info:
        return {
            "country": "Unknown",
            "bank": "Unknown",
            "scheme": "Unknown",
            "type": "Unknown",
            "brand": "Unknown"
        }
    return {
        "country": f"{bin_info['country']['name']} ({bin_info['country']['alpha2']}) {bin_info['country'].get('emoji', '')}",
        "bank": bin_info['bank']['name'] if bin_info.get('bank') else 'Unknown',
        "scheme": bin_info.get('scheme', 'Unknown'),
        "type": bin_info.get('type', 'Unknown'),
        "brand": bin_info.get('brand', 'Unknown')
    }

@app.before_request
def assign_request_id():
    g.request_id = random.randint(100000, 999999)

@app.route('/api/ccgenerator', methods=['GET'])
def cc_generator():
    try:
        bin_input = request.args.get('bin', '')
        count = min(int(request.args.get('count', 1)), 100)
        formatted = request.args.get('formatted', 'true').lower() == 'true'
        plaintext = request.args.get('plaintext', 'false').lower() == 'true'

        if not bin_input:
            return jsonify({'error': 'BIN parameter is required'}), 400

        if not validate_bin_format(bin_input):
            return jsonify({'error': 'Invalid BIN format'}), 400

        raw_bin, exp_month, exp_year, cvv = parse_bin_input(bin_input)
        partial_bin = raw_bin.replace('x', '')
        card_type = detect_card_type(partial_bin)
        card_length = get_card_length(card_type)

        generated_cards = []
        for _ in range(count):
            card_number = generate_card_number(partial_bin, card_length)
            detected_type = detect_card_type(card_number)
            final_cvv = cvv if cvv else generate_cvv(detected_type)
            exp = f"{exp_month}|{exp_year}"

            if plaintext:
                generated_cards.append(f"{card_number}|{exp}|{final_cvv}")
            else:
                if formatted:
                    formatted_number = (
                        f"{card_number[:4]} {card_number[4:10]} {card_number[10:]}"
                        if detected_type == 'amex'
                        else ' '.join([card_number[i:i+4] for i in range(0, len(card_number), 4)])
                    )
                    generated_cards.append({
                        'card_number': formatted_number,
                        'raw_card_number': card_number,
                        'expiry': f"{exp_month}/{exp_year[-2:]}",
                        'expiry_month': exp_month,
                        'expiry_year': exp_year,
                        'cvv': final_cvv,
                        'card_type': detected_type,
                        'formatted': True
                    })
                else:
                    generated_cards.append({
                        'card': f"{card_number}|{exp}|{final_cvv}",
                        'card_number': card_number,
                        'expiry_month': exp_month,
                        'expiry_year': exp_year,
                        'cvv': final_cvv,
                        'card_type': detected_type,
                        'formatted': False
                    })

        metadata = get_bin_metadata(partial_bin[:6])

        if plaintext:
            return '\n'.join(generated_cards), 200, {'Content-Type': 'text/plain'}

        return jsonify({
            'status': 'success',
            'request_id': g.request_id,
            'request': {
                'bin': bin_input,
                'count': count,
                'formatted': formatted
            },
            'metadata': metadata,
            'generated': generated_cards
        })

    except Exception as e:
        logger.error(f"Error generating cards: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.errorhandler(400)
def bad_request(error):
    return jsonify({'error': 'Bad request', 'message': str(error)}), 400

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found', 'message': str(error)}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error', 'message': str(error)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
