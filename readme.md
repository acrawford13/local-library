# Item Catalog Project

This is a catalog of books, which uses Google Maps API to allow searching for books in the local area.

## Getting Started
- Download the repository
- Create a new project in Google APIs and ensure the following APIs are enabled:
  - Google Maps Geocoding API
  - Google Maps JavaScript API
  - Google Places API Web Service
- Update the following files with your own api keys/client secrets:
  - `fb_client_secret.json`
  - `google_client_secret.json`
  - `google_api_key.json`
- Update Google client id and Facebook app id in `login.html`, lines 11 & 48
- From the main folder, run `python populatedb.py` to populate the database with sample data
- Run `python views.py` to start the server

## Dependencies
- Flask
- SQL Alchemy
- [Python Client for Google Maps Services](https://github.com/googlemaps/google-maps-services-python)  
(`$ pip install -U googlemaps`)
- OAuth2Client

## API Keys/Credentials
- [Google Maps API key](https://github.com/googlemaps/google-maps-services-python#api-keys)  
- Facebook App ID/App Secret
- Google OAuth 2.0 Web Client ID/Client Secret

## API Endpoints
**GET** api/search/  
Accepts search parameters and returns books within the search area, including distance (in km) from the search point

| parameter |  |
|--|--|
| `radius` | **required:** the search radius in km |
| `lat` | latitude to search location |
| `lng` | longitude of search location |
| `search` | a search term, eg. '10 Macquarie St., Sydney ' |

You must provide `lat` and `lng` parameters, or the `search` parameter:  
`/api/search/?radius=10&lat=-33.8689596&lng=151.2126585`  
`/api/search/?radius=10&search=10%20Macquarie%20St.,%20Sydney`  

#### Sample response

    {
      "books": [
        {
          "author": "Haruki Murakami",
          "date_added": "Tue, 03 Oct 2017 10:18:09 GMT",
          "description": "In a Tokyo suburb...",
          "name": "The Wind-Up Bird Chronicle",
          "slug": "the-wind-up-bird-chronicle",
          "distance": 2.07,
          "owner" : {
            "username": "andrea-crawford",
            "name": "Andrea Crawford",
            "city": "Sarajevo",
            "country": "Bosnia and Herzegovina",
            "picture": "profilepic.jpg"        
          }
        },
        ...
      ]
    }

**GET** api/user/[username]  
Returns a JSON object with the user's details and owned books:

#### Sample response

    {
      "username": "andrea-crawford",
      "name": "Andrea Crawford",
      "city": "Sarajevo",
      "country": "Bosnia and Herzegovina",
      "picture": "profilepic.jpg"
      "books": [
        {
          "author": "Haruki Murakami",
          "date_added": "Tue, 03 Oct 2017 10:18:09 GMT",
          "description": "In a Tokyo suburb...",
          "name": "The Wind-Up Bird Chronicle",
          "slug": "the-wind-up-bird-chronicle"
        },
        ...
      ]
    }

**GET** api/book/[username]/[bookslug]  
Returns a JSON object with the book and its owner's details

#### Sample response

    {
      "author": "Haruki Murakami",
      "date_added": "Tue, 03 Oct 2017 10:18:09 GMT",
      "description": "In a Tokyo suburb...",
      "name": "The Wind-Up Bird Chronicle",
      "slug": "the-wind-up-bird-chronicle",
      "owner" : {
        "username": "andrea-crawford",
        "name": "Andrea Crawford",
        "city": "Sarajevo",
        "country": "Bosnia and Herzegovina",
        "picture": "profilepic.jpg"        
      }
    }
