from flask import Flask, request, g, redirect, abort, render_template, url_for, jsonify
import requests
import logging
import json
import time

import config

ROOT_URL = 'https://api.twotap.com'

app = Flask(__name__)
app.config.from_object(config)

# configure logging
stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
app.logger.addHandler(stream_handler)

@app.route('/')
def index():
    return render_template('index.html')


# receives a product url and triggers a purchase for that product
@app.route('/purchase', methods=['POST'])
def purchase():
    product_url = request.form.get('product_url', None)
    if product_url is None:
        abort(403)

    return render_template('purchase_done.html', result=purchase_product(product_url))


# this is where TwoTap asks us to confirm the purchase with the private token
@app.route('/purchase_confirm', methods=['POST'])
def purchase_confirm():
    body = request.get_json()

    purchase_id = body['purchase_id']

    response = requests.post(ROOT_URL + '/v1.0/purchase/confirm',
            params={'private_token': app.config['TT_PRIVATE_TOKEN']},
            headers={'content-type': 'application/json'},
            data=json.dumps({'purchase_id': purchase_id}))

    log_response('Confirmed Purchase {}'.format(purchase_id), response.json())

    return jsonify(response.json())


# this is where TwoTap lets us know that a purchase is done; an alternative to polling for the result
# this is NOT called when running requests with fake_confirm
@app.route('/purchase_finished', methods=['POST'])
def purchase_finished():
    print 'PURCHASE FINISHED CALLED'
    return ''


# this is only an example of the TwoTap flow
# in a real application this would probably be executed in an asynchronous task
def purchase_product(product_url):
    # add the product to cart
    print "Adding '{}' to cart".format(product_url)
    response = requests.post(ROOT_URL + '/v1.0/cart',
            headers={'content-type': 'application/json'},
            params={'public_token': app.config['TT_PUBLIC_TOKEN'], 'test_mode': app.config['TT_TEST_MODE']},
            data=json.dumps({'products': [product_url]}))

    log_response('Added to cart', response.json())

    cart_id = str(response.json()['cart_id'])

    # poll for the cart status
    while response.json()['message'] == 'still_processing':
        time.sleep(2)
        response = requests.get(ROOT_URL + '/v1.0/cart/status',
            params={'public_token': app.config['TT_PUBLIC_TOKEN'], 'cart_id': cart_id, 'test_mode': app.config['TT_TEST_MODE']})

        log_response('Checking status for cart {}'.format(cart_id), response.json())

    if response.json()['message'] != 'done':
        return 'failed'

    fields_input = make_fields_input(response.json()['sites'])

    # trigger the purchase
    response = requests.post(ROOT_URL + '/v1.0/purchase',
            params={'public_token': app.config['TT_PUBLIC_TOKEN'], 'test_mode': app.config['TT_TEST_MODE']},
            headers={'content-type': 'application/json'},
            data=json.dumps({
                'cart_id': cart_id,
                'fields_input': fields_input,
                'products': [product_url],
                'confirm': {
                    'method': 'sms', # we want the user to confirm by sms
                    'phone': '5555555555',
                    'sms_confirm_url': url_for('purchase_confirm', _external=True),
                    'sms_finished_url': url_for('purchase_finished', _external=True),
                    },
                }))

    purchase_id = response.json()['purchase_id']

    log_response('Triggered purchase {}'.format(purchase_id), response.json())

    # poll for the purchase status

    while response.json()['message'] == 'still_processing':
        time.sleep(2)
        response = requests.get(ROOT_URL + '/v1.0/purchase/status',
            params={'public_token': app.config['TT_PUBLIC_TOKEN'], 'purchase_id': purchase_id, 'test_mode': app.config['TT_TEST_MODE']})

        log_response('Checking status for purchase {}'.format(purchase_id), response.json())

    return response.json()['message']


# dummy checkout data
NOAUTH_CHECKOUT_DEFAULT = { 
        'email': 'shopper@gmail.com',
        'shipping_title': 'Mr',
        'shipping_first_name': 'John',
        'shipping_last_name': 'Smith',
        'shipping_telephone': '5555555555',
        'shipping_zip': '94303',
        'shipping_state': 'California',
        'shipping_city': 'Palo Alto',
        'shipping_country': 'United States of America',
        'shipping_address': '555 Palo Alto Avenue',
        'billing_title': 'Mr',
        'billing_first_name': 'John',
        'billing_last_name': 'Smith',
        'billing_telephone': '5555555555',
        'billing_zip': '94303',
        'billing_state': 'California',
        'billing_city': 'Palo Alto',
        'billing_country': 'United States of America',
        'billing_address': '555 Palo Alto Avenue',
        'card_type': 'Visa',
        'card_number': '4111111111111111',
        'card_name': 'John Smith',
        'expiry_date_year': '2018',
        'expiry_date_month': '09',
        'cvv': '123',
        }


def make_fields_input(cart_sites):
    fields_input = {}
    # for all products set quantity = 1
    # for all other options select the last entry in the list of available  values
    for site_id, site in cart_sites.items():
        fields_input[site_id] = {'noauthCheckout': NOAUTH_CHECKOUT_DEFAULT, 'addToCart': {}}
        for product_md5, product_required_fields in site['add_to_cart'].items():
            fields_input[site_id]['addToCart'][product_md5] = {'quantity': 1}
            for field, spec in product_required_fields['required_fields'].items():
                if field != 'quantity':
                    fields_input[site_id]['addToCart'][product_md5][field] = product_required_fields['required_field_values'][field][-1]['value']

    return fields_input


def log_response(message, response_body):
    print ">>>>> {} >>>>>".format(message)
    print json.dumps(response_body, indent=2)
    print


if __name__ == '__main__':
    app.run()