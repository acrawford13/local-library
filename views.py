from flask import Flask, render_template, flash, url_for
from flask import redirect, request, jsonify, make_response
from flask import session as login_session

from sqlalchemy import create_engine, and_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from models import Base, Book, User

import json
from datetime import datetime
from math import sqrt
import httplib2

# for saving user images:
from werkzeug.utils import secure_filename
import os
# to generate state token:
import random
import string
# to access google maps api:
import googlemaps
# to 'slugify' username:
import re
# for google authentication:
import requests
from oauth2client.client import flow_from_clientsecrets, FlowExchangeError

UPLOAD_FOLDER = 'static/images/'
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

engine = create_engine('sqlite:///catalog.db')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

GOOGLE_API_KEY = json.load(open('google_api_key.json'))['key']
gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

FACEBOOK_APP_ID = (json.loads(open('fb_client_secret.json', 'r').read())
                   ['web']['app_id'])
FACEBOOK_APP_SECRET = (json.loads(open('fb_client_secret.json', 'r').read())
                       ['web']['app_secret'])
GOOGLE_CLIENT_SECRET_FILE = 'google_client_secret.json'


# csrf protection snippet from http://flask.pocoo.org/snippets/3/
# check state token matches on post requests
@app.before_request
def csrf_protect():
    if request.method == 'POST':
        token = login_session.get('csrf_token', None)
        if not token or (token != request.form.get('csrf_token') and
                         token != request.args.get('csrf_token')):
            response = make_response(json.dumps('Invalid state'), 401)
            response.headers['Content-Type'] = 'application/json'
            return response


# generate a random state token if none exists
def generate_csrf_token():
    if 'csrf_token' not in login_session:
        login_session['csrf_token'] = (''.join(random.choice(
            string.ascii_uppercase + string.digits) for x in xrange(32)))
    return login_session['csrf_token']

# make csrf token function available to template files
app.jinja_env.globals['csrf_token'] = generate_csrf_token


# check that uploaded files match the allowed extensions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# remove spaces and replace non-letters/numbers with hyphens in a given string
def slugify(name):
    string = re.sub(r'\s{2,}', '', name)
    string = re.sub(r'[^\w\d\s]', '', string)
    string = re.sub(r'[^\w\d]', '-', string)
    return string.lower()


# create/fetch user, and add username to login session
def loginUser(name, email, picture):
    user = session.query(User).filter_by(email=email).one_or_none()

    if user:
        if user.location_lat:
            login_session['location_lat'] = user.location_lat
            login_session['location_lng'] = user.location_lng
    else:
        user = User(
            username=slugify(name),
            name=name,
            email=email,
            picture=picture
        )
        session.add(user)

        # if the username is not unique add a number to the end
        for attempt in range(1, 20):
            try:
                session.commit()
                break
            except IntegrityError:
                session.rollback()
                user.username = slugify(name) + "-" + str(attempt)
                session.add(user)

    login_session['username'] = user.username
    return user


@app.route('/')
def home():
    if 'location_lat' in login_session:
        location = {'lat': login_session['location_lat'],
                    'lng': login_session['location_lng']}
        search_radius = 20
        search_radius_deg = (search_radius/111.0)**2

        # get all books within the search radius
        books = (session.query(Book).join(User)
                        .filter(and_(
                                User.distance(location) <= search_radius_deg,
                                User.username != login_session['username']))
                        .order_by(User.distance(location), Book.name).all())
        return render_template('home-logged-in.html',
                               books=books, search_radius=search_radius,
                               location=location, api_key=GOOGLE_API_KEY)
    else:
        books = session.query(Book).order_by('date_added').limit(5)
        return render_template('home-logged-out.html',
                               books=books, api_key=GOOGLE_API_KEY)


@app.route('/login/')
def showLogin():
    if 'username' in login_session:
        return redirect(url_for('home'))
    return render_template('login.html')


@app.route('/fbconnect', methods=['POST'])
def fbconnect():
    access_token = request.data

    url = ('https://graph.facebook.com/oauth/access_token?grant_type=fb_exchange_token&client_id=%s&client_secret=%s&fb_exchange_token=%s'
           % (FACEBOOK_APP_ID, FACEBOOK_APP_SECRET, access_token))
    h = httplib2.Http()
    response = h.request(url, 'GET')[1]
    login_session['app_access_token'] = json.loads(response)['access_token']

    url = ('https://graph.facebook.com/me?fields=name,id,email&access_token=%s'
           % login_session['app_access_token'])
    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    user_data = json.loads(result)

    if 'email' not in user_data:
        response = make_response(
                   json.dumps("Sorry, email address is required for login"),
                   400)
        response.headers['Content-Type'] = 'application/json'
        return response

    login_session['facebook_id'] = user_data['id']
    login_session['provider'] = "facebook"

    url = ('https://graph.facebook.com/me/picture?redirect=0&height=80&width=80&access_token=%s'
           % login_session['app_access_token'])

    h = httplib2.Http()
    result = h.request(url, 'GET')[1]
    user_picture = json.loads(result)['data']

    user = loginUser(name=user_data['name'],
                     email=user_data['email'],
                     picture=user_picture['url'])

    return url_for('home')


@app.route('/gconnect', methods=['POST'])
def gconnect():
    code = request.data
    client_id = (json.loads(open(GOOGLE_CLIENT_SECRET_FILE, 'r').read())
                 ['web']['client_id'])

    try:
        oauth_flow = flow_from_clientsecrets(GOOGLE_CLIENT_SECRET_FILE,
                                             scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(json.dumps(
                   'Failed to upgrade the authorisation code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])

    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(json.dumps(
                   "Token's user ID doesn't match given user ID"), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    if result['issued_to'] != client_id:
        response = make_response(json.dumps(
                   "Token's client ID doesn't match application's ID"), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_credentials = login_session.get('credentials')
    stored_gplus_id = login_session.get('gplus_id')

    if stored_credentials is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps("User is already connected"), 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id
    login_session['provider'] = "google"

    # get user info
    userinfo_url = 'https://www.googleapis.com/oauth2/v2/userinfo'
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = json.loads(answer.text)

    user = loginUser(name=data['name'],
                     email=data['email'],
                     picture=data['picture'])

    return redirect(url_for('home'))


@app.route('/logout/')
def logout():
    if login_session['provider'] == 'facebook':
        fbdisconnect()
    elif login_session['provider'] == 'google':
        gdisconnect()

    del login_session['username']
    if 'location_lat' in login_session:
        del login_session['location_lat']
        del login_session['location_lng']
    del login_session['provider']

    return redirect(url_for('home'))


@app.route('/fbdisconnect/')
def fbdisconnect():
    facebook_id = login_session['facebook_id']
    access_token = login_session['app_access_token']
    h = httplib2.Http()
    url = ("https://graph.facebook.com/%s/permissions?access_token=%s"
           % (facebook_id, access_token))
    result = json.loads(h.request(url, 'DELETE')[1])

    del login_session['facebook_id']
    del login_session['app_access_token']

    if 'success' in result:
        return "you have been logged out"
    return "you were not able to be logged out"


@app.route('/gdisconnect/')
def gdisconnect():
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(json.dumps('User not connected'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    url = 'http://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]

    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']

        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response = make_response(json.dumps('Failed to revoke token'), 400)
        response.headers['Content-Type'] = 'application/json'
        return response


@app.route('/search/')
def search():
    location = {}

    if "search" in request.args:
        try:
            location = (gmaps.geocode(request.args.get('search'))
                        [0]['geometry']['location'])
        except googlemaps.exceptions.TransportError:
            response = make_response(
                json.dumps('Request to Google Maps API was unsuccessful'), 408)
            response.headers['Content-Type'] = 'application/json'
            return response
        search_radius = float(request.args.get('radius', 10))
    elif "radius" in request.args and login_session['location_lat']:
        search_radius = float(request.args.get('radius'))
        location['lat'] = login_session['location_lat']
        location['lng'] = login_session['location_lng']

    # convert search radius km to degrees (approx.)
    # then square the value to compare with the User.distance(location) result
    # because sqlite doesn't natively support sqrt
    search_radius_deg = (search_radius/111.0)**2

    if 'username' in login_session:
        # get all books within the search radius
        books = (session
                 .query(Book)
                 .join(User)
                 .filter(and_(User.distance(location) <= search_radius_deg,
                              User.username != login_session['username']))
                 .order_by(User.distance(location), Book.name).all())
    else:
        # get all books within the search radius
        books = (session.query(Book).join(User)
                        .filter(User.distance(location) <= search_radius_deg)
                        .order_by(User.distance(location), Book.name).all())
    if books:
        return make_response(render_template('_search-list.html',
                             books=books, location=location), 200)
    else:
        return ('No results within %skm of %s' %
                (request.args.get('radius'),
                 request.args.get('search', 'your location')))


@app.route('/api/search/')
def showJson():
    # search radius in km
    location = {}

    search_radius = float(request.args.get('radius', 10))
    location['lat'] = request.args.get('lat')
    location['lng'] = request.args.get('lng')
    search_term = request.args.get('search')

    if search_term:
        location = (gmaps.geocode(request.args.get('search'))
                    [0]['geometry']['location'])

    search_radius_deg = (search_radius/111.0)**2
    books = (session.query(Book).join(User)
             .filter(User.distance(location) <= search_radius_deg)
             .order_by(User.distance(location), Book.name).all())

    return jsonify(books=[book.serialize_detailed(location=location)
                          for book in books])


@app.route('/api/user/<string:username>/')
def userJSON(username):
    user = session.query(User).filter_by(username=username).one_or_none()

    if not user:
        return "No user by this name"

    books = session.query(Book).filter_by(owner_username=username).all()
    return jsonify(name=user.name,
                   city=user.city,
                   country=user.country,
                   picture=user.picture,
                   books=[book.serialize_simple for book in books])


@app.route('/api/book/<string:username>/<string:bookslug>')
def bookJSON(username, bookslug):
    book = (session.query(Book).filter_by(owner_username=username)
                               .filter_by(slug=bookslug).one_or_none())

    if not book:
        return "No book by this name"

    return jsonify(book.serialize_detailed())


@app.route('/<string:username>/editprofile/', methods=['GET', 'POST'])
def editProfile(username):
    # check if a user is logged in
    if 'username' not in login_session:
        flash("Please log in to edit your profile")
        return redirect(url_for('showLogin'))

    # check if logged in user matches the username in the URL
    # if not, redirect to the correct username
    if login_session['username'] != username:
        return redirect(url_for('editProfile',
                                username=login_session['username']))

    user = session.query(User).filter_by(username=username).one()

    # get request: render form to edit user profile
    if request.method == 'GET':
        return render_template('edit-profile.html',
                               user=user, api_key=GOOGLE_API_KEY)

    # post request: update user info in database
    if request.method == 'POST':
        # upload profile picture to upload folder
        if 'profilepic' in request.files:
            file = request.files['profilepic']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                user.picture = filename

        # store the data from the form
        form = request.form

        user.name = form['name']
        user.city = form['city']
        user.country = form['country']
        user.location_lat = float(form['location_lat'])
        user.location_lng = float(form['location_lng'])
        login_session['location_lat'] = float(form['location_lat'])
        login_session['location_lng'] = float(form['location_lng'])
        session.commit()
        return redirect(url_for('showUser', username=username))


@app.route('/<string:username>/')
def showUser(username):
    location = {}
    if 'location_lat' in login_session:
        location = {'lat': login_session['location_lat'],
                    'lng': login_session['location_lng']}

    books = session.query(Book).filter_by(owner_username=username).all()
    user = session.query(User).filter_by(username=username).one_or_none()
    if not user:
        flash("The user <strong>%s</strong> does not exist" % username)
        return redirect(url_for('home'))
    return render_template('user-profile.html',
                           user=user, books=books, location=location)


@app.route('/<string:username>/<string:bookslug>')
def showBook(username, bookslug):
    book = (session.query(Book).filter_by(owner_username=username)
                               .filter_by(slug=bookslug).one_or_none())

    # check if book exists
    if book:
        return render_template('book.html', book=book)
    else:
        flash("This book does not exist")
        return redirect(url_for('home'))


@app.route('/<string:username>/new', methods=['GET', 'POST'])
def newBook(username):
    # check if a user is logged in
    if 'username' not in login_session:
        flash("Please log in to add a book")
        return redirect(url_for('showLogin'))

    # check if logged in user matches the username in the URL
    # if not, redirect to the correct username
    if login_session['username'] != username:
        return redirect(url_for('newBook', username=login_session['username']))

    # get request: render a form to add a new book
    if request.method == 'GET':
        return render_template('new-book.html')

    # post request: add new book to the database
    elif request.method == 'POST':
        # store the data from the form
        form = request.form

        # create new book object
        book = Book(name=form['name'],
                    slug=slugify(form['name']),
                    author=form['author'],
                    description=form['description'],
                    date_added=datetime.now(),
                    owner_username=username)
        session.add(book)

        # if the book slug + username unique constraint fails,
        # add a number to the end of the book slug
        for attempt in range(1, 20):
            try:
                session.commit()
                break
            except IntegrityError:
                session.rollback()
                book.slug = slugify(form['name']) + "-" + str(attempt)
                session.add(book)
        return redirect(url_for('showBook',
                        username=username, bookslug=book.slug))


@app.route('/<string:username>/<string:bookslug>/edit',
           methods=['GET', 'POST'])
def editBook(username, bookslug):
    # check if a user is logged in
    if 'username' not in login_session:
        flash("Please <a href='%s'>log in</a> to edit this book"
              % url_for('showLogin'))
        return redirect(url_for('showBook',
                                username=username, bookslug=bookslug))

    # check if logged in user owns the book
    if login_session['username'] != username:
        flash("This is not your book")
        return redirect(url_for('showBook',
                                username=username, bookslug=bookslug))

    # get the book object that matches username & slug
    book = (session.query(Book).filter_by(owner_username=username)
                               .filter_by(slug=bookslug).one_or_none())

    # check if the book exists
    if not book:
        flash("This book does not exist")
        return redirect(url_for('home'))

    # get request: render a form to edit the book's details
    if request.method == 'GET':
        return render_template('edit-book.html', book=book)

    # post request: update the book's details in the database
    elif request.method == 'POST':
        # store the data from the form
        form = request.form

        # if the name has changed, generate a new slug
        if book.name != form['name']:
            book.slug = slugify(form['name'])

        book.name = form['name']
        book.author = form['author']
        book.description = form['description']

        # if the book slug + username unique constraint fails,
        # add a number to the end of the book slug
        for attempt in range(1, 20):
            try:
                session.commit()
                break
            except IntegrityError:
                session.rollback()
                book.name = form['name']
                book.author = form['author']
                book.description = form['description']
                book.slug = slugify(form['name']) + "-" + str(attempt)
        return redirect(url_for('showBook',
                                username=username, bookslug=book.slug))


@app.route('/<string:username>/<string:bookslug>/delete',
           methods=['GET', 'POST'])
def deleteBook(username, bookslug):
    # check if a user is logged in
    if 'username' not in login_session:
        flash("Please <a href='%s'>log in</a> to delete this book"
              % url_for('showLogin'))
        return redirect(url_for('showBook',
                                username=username, bookslug=bookslug))

    # check if logged in user owns the book
    if login_session['username'] != username:
        flash("This is not your book")
        return redirect(url_for('showBook',
                                username=username, bookslug=bookslug))

    # get the book object that matches username & slug
    book = (session.query(Book).filter_by(owner_username=username)
                               .filter_by(slug=bookslug).one_or_none())

    # check if the book exists
    if not book:
        flash("This book does not exist")
        return redirect(url_for('home'))

    # get request: render a confirmation page
    if request.method == 'GET':
        return render_template('delete-book.html', book=book)

    # post request: delete the book and redirect to the user's profile
    elif request.method == 'POST':
        session.delete(book)
        session.commit()
        flash("<strong>%s</strong> has been deleted" % book.name)
        return redirect(url_for('showUser', username=username))

if __name__ == '__main__':
    app.debug = True
    app.secret_key = 'make_this_better'
    app.run(host='0.0.0.0', port=5000)
