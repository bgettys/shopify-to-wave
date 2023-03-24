from typing import Union, Any

import requests
from dotenv import load_dotenv
from os import environ
import shopify
from shopify import Product

load_dotenv()
shopify_shop_name = environ.get("SHOPIFY_SHOP_NAME")
if shopify_shop_name is None:
    print("shopify shop name not provided. bailing out")
    exit(1)
wave_access_token = environ.get("WAVE_ACCESS_TOKEN")
if wave_access_token is None:
    print("wave access token not provided. bailing out")
    exit(1)
wave_business_name = environ.get("WAVE_BUSINESS_NAME")
if wave_business_name is None:
    print("wave business name not provided. bailing out")
    exit(1)
wave_debit_account_name = environ.get("WAVE_DEBIT_ACCOUNT_NAME")
if wave_debit_account_name is None:
    print("wave debit account name not provided. bailing out")
    exit(1)
wave_credit_account_name = environ.get("WAVE_CREDIT_ACCOUNT_NAME")
if wave_credit_account_name is None:
    print("wave credit account name not provided. bailing out")
    exit(1)
print(f"preparing to connect to shopify store {shopify_shop_name}")
shopify_api_key = environ.get("SHOPIFY_API_KEY")
shopify_password = environ.get("SHOPIFY_PASSWORD")
if shopify_api_key is not None and shopify_password is not None:
    shop_url = f"https://%s:%s@{shopify_shop_name}.myshopify.com/admin" % (shopify_api_key, shopify_password)
    shopify.ShopifyResource.set_site(shop_url)
else:
    shopify_access_token = environ.get("SHOPIFY_ACCESS_TOKEN")
    if shopify_access_token is None:
        print("neither api key + password nor access token were given. bailing out")
        exit(1)
    session = shopify.Session(f"{shopify_shop_name}.myshopify.com", '2022-04', shopify_access_token)
    shopify.ShopifyResource.activate_session(session)

shop = shopify.Shop.current
products = shopify.Product.find()
prd_data: list[dict[str, Union[str, float]]] = []
for p in products:
    prd = dict[str, Union[str, float]] = {}
    product: Product = p
    attributes = product.attributes
    variants = attributes['variants']
    for variant in variants:
        inv_item_id = variant.attributes['inventory_item_id']
        inv_item = shopify.InventoryItem.find(inv_item_id)
        inv_attrs = inv_item.attributes
        if inv_attrs['cost'] is not None:
            prd['cost'] = inv_attrs['cost']

    if 'cost' in prd:
        prd['title'] = attributes['title']
        prd['created_at'] = attributes['created_at']
        prd['product_type'] = attributes['product_type']
        prd['handle'] = attributes['handle']
        prd_data.append(prd)

headers={'Authorization': 'Bearer ' + wave_access_token}
print('wave business name: ' + wave_business_name)
post_data = """


    query {
      businesses(page: 1, pageSize: 10) {
        pageInfo {
          currentPage
          totalPages
          totalCount
        }
        edges {
          node {
            name
            accounts {
                edges {
                    node {
                        id
                        name
                    }
                }
            }
          }
        }
      }
    }


"""

print('post data: ' + post_data)
resp = requests.post('https://gql.waveapps.com/graphql/public', headers=headers, json={"query": post_data})
print(resp.status_code)
debit_account_id = None
credit_account_id = None
business_id = None
if resp.status_code == 200:
    json = resp.json()
    if json is None:
        print('failed to retrieve business data, bailing')
        exit(1)
    for edge_data in json['data']['businesses']['edges']:
        print(edge_data)
        if edge_data['node']['name'] == wave_business_name:
            business_id = edge_data['node']['id']
            for account_edge in edge_data['node']['accounts']['edges']:
                if account_edge['node']['name'] == wave_debit_account_name:
                    debit_account_id = account_edge['node']['name']
                if account_edge['node']['name'] == wave_credit_account_name:
                    credit_account_id = account_edge['node']['name']
    if business_id is None:
        print('failed to find a business named %s' % wave_business_name)
        exit(1)
    if debit_account_id is None:
        print('failed to find a debit account named %s' % wave_debit_account_name)
        exit(1)
    if credit_account_id is None:
        print('failed to find a credit account named %s' % wave_credit_account_name)
        exit(1)

elif resp.status_code == 400:
    print(f'failed to query businesses: {resp.content}')
    exit(1)

for prd in prd_data:
    post_data = """
      mutation ($input:MoneyTransactionCreateInput!){
        moneyTransactionCreate(input:$input){
          didSucceed
          inputErrors{
            path
            message
            code
          }
          transaction{
            id
          }
        }
      }
          
    """
    input_data = {
          "businessId": business_id,
          "externalId": "some-reference-id",
          "date": "2021-02-05",
          "description": "My first sale",
          "anchor": {
            # Eg. Business checking account
            "accountId": "<ANCHOR_ACCOUNT_ID>",
            "amount": 100.00,
            "direction": "DEPOSIT"
          },
          "lineItems": [{
            "accountId": debit_account_id,
            "amount": prd['cost'],
            "balance": "DEBIT"
          },{
              "accountId": credit_account_id,
              "amount": prd['cost'],
              "balance": "CREDIT"
          }]
    }
    resp = requests.post('https://gql.waveapps.com/graphql/public', headers=headers, json={"query": post_data, "input": input_data})