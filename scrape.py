import os
import argparse
import requests

def main():
    parser = argparse.ArgumentParser(prog='Skylight Scraper', description='Syncs photos from a Skylight frame to a local directory')
    parser.add_argument('-f', '--frame', required=True, type=int, help='Numeric ID of the frame to download from')
    parser.add_argument('-a', '--auth', required=True, help='Base64 string from Authorization header')
    parser.add_argument('-o', '--output', required=True, help='Directory to download photos to')
    parser.add_argument('-s', '--senders', help='Only download photos sent by these email addresses (comma separated)')
    args = parser.parse_args()
    
    photos = []
    url = f'https://app.ourskylight.com/api/frames/{args.frame}/messages'
    page, num_pages = 1, 0
    while True:
        res = requests.get(f'{url}?page={page}', headers={'Authorization': f'Basic {args.auth}'}).json()
        if num_pages == 0:
            num_pages = int(res['meta']['num_pages'])
        photos += [{
            'key': photo['attributes']['asset_key'],
            'timestamp': photo['attributes']['created_at'],
            'from': photo['attributes']['from_email'],
            'url': photo['attributes']['asset_url']
        } for photo in res['data']]
        page += 1
        if page > num_pages:
            break
    
    print(f'Found {len(photos)} photos.')

    if not os.path.isdir(args.output):
        os.makedirs(args.output)

    files = [f for f in os.listdir(args.output) if os.path.isfile(os.path.join(args.output, f))]
    for photo in photos:
        if args.senders and photo['from'] not in args.senders.split(','):
            continue
        filename = f"{photo['timestamp']}_{photo['from']}_{photo['key']}"
        if filename not in files:
            destination = os.path.join(args.output, filename)
            print(f'Saving {destination}')
            image = requests.get(photo['url']).content
            with open(destination, 'wb') as f:
                f.write(image)
    
    print('Done.')

if __name__ == '__main__':
    main()