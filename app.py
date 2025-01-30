from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
import MySQLdb.cursors
import os
import math
import json
import time
from werkzeug.utils import secure_filename
from urllib.parse import unquote_plus
import service_routes  # Import the new module

app = Flask(__name__)

# Set secret key for session management
app.secret_key = os.urandom(24)

#adding additional routes for service calls for server restart and db backup
app.register_blueprint(service_routes.service_routes)

# Database connection parameters
app.config['MYSQL_HOST'] = 'nmdb.nepalmusicarchive.org'
app.config['MYSQL_USER'] = 'nmdbuse'
# app.config['MYSQL_PASSWORD'] = 'XtDs7r8e1sKNjD'
app.config['MYSQL_PASSWORD'] = 'ZVAx2zxd&oHW^aME'
app.config['MYSQL_DB'] = 'nmdb'
app.config['MYSQL_PORT'] = 33060
app.config['MYSQL_CHARSET'] = 'utf8mb4'
# server = os.getenv("NTFY_SERVER")
# subscription = os.getenv("NTFY_SUBSCRITION")

# Initialize MySQL
mysql = MySQL(app)

# Session timeout settings
SESSION_LIFETIME = 3600

@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = SESSION_LIFETIME

@app.route('/header')
def header():
    return render_template('a/header.html')

@app.route('/', methods=['GET'])
def index():
    connection = mysql.connect
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)

    search_query = request.args.get('search', '').strip()
    letter = request.args.get('letter', '').strip().upper()  # Get the letter parameter from the URL

    # Handle '0-9' case
    if letter == '0-9':
        letter = '0'
    elif len(letter) != 1 or not (letter.isalpha() or letter == '0'):
        letter = ''  # Default to empty if invalid

    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page
    
    # Build the base query and parameters
    query = "SELECT COUNT(*) as total FROM musicians WHERE 1=1"
    params = []

    # Add search filter
    if search_query:
        query += " AND musicians_english LIKE %s"
        params.append('%' + search_query + '%')

    # Add letter filter
    if letter:
        if letter == '0':
            query += " AND musicians_english REGEXP '^[0-9]'"
        else:
            query += " AND musicians_english LIKE %s"
            params.append(letter + '%')
    
    # Execute count query
    cursor.execute(query, tuple(params))
    result = cursor.fetchone()
    total_musicians = result['total'] if result else 0
    
    total_pages = math.ceil(total_musicians / per_page) if total_musicians > 0 else 1
    
    # Build the selection query and parameters
    query = "SELECT musician_id AS id, musicians_english AS name, cover_image, type, gender "
    query += "FROM musicians WHERE 1=1"
    params = []

    # Add search filter
    if search_query:
        query += " AND musicians_english LIKE %s"
        params.append('%' + search_query + '%')

    # Add letter filter
    if letter:
        if letter == '0':
            query += " AND musicians_english REGEXP '^[0-9]'"
        else:
            query += " AND musicians_english LIKE %s"
            params.append(letter + '%')

    # Order and limit
    query += " ORDER BY musicians_english LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
    
    # Execute selection query
    cursor.execute(query, tuple(params))
    musicians = cursor.fetchall()
    cursor.close()

    for musician in musicians:
        musician['encoded_name'] = unquote_plus(musician['name']).replace('%20', '-')
    
    return render_template(
        'index.html',
        musicians=musicians,
        page=page,
        total_pages=total_pages,
        search=search_query,
        letter=letter
    )

@app.route('/a')
def redirect_to_login():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'last_activity' in session:
        if (time.time() - session['last_activity']) > SESSION_LIFETIME:
            session.clear()
            return redirect(url_for('login'))
    
    session['last_activity'] = time.time()

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        connection = mysql.connect
        cursor = connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM login WHERE username = %s AND password = %s', (username, password))
        user = cursor.fetchone()
        cursor.close()
        
        if user:
            session['loggedin'] = True
            session['username'] = user['username']
            return redirect(url_for('dashboard'))  # Redirect to your dashboard or other page
        else:
            flash('Incorrect username or password', 'danger')
    
    return render_template('a/index.html')

@app.route('/dashboard')
def dashboard():
    if 'loggedin' in session:
        connection = mysql.connect
        cursor = connection.cursor(MySQLdb.cursors.DictCursor)

        # Get total number of musicians
        cursor.execute('SELECT COUNT(*) AS total_musicians FROM musicians')
        total_musicians = cursor.fetchone()['total_musicians']

        # Get count of artists, bands, and non-professionals from the musicians table
        cursor.execute("SELECT type, COUNT(*) AS count FROM musicians GROUP BY type")
        counts = cursor.fetchall()

        # Initialize counts
        total_artists = 0
        total_bands = 0
        total_non_professional = 0

        # Aggregate counts based on type
        for row in counts:
            if row['type'] == 'artist':
                total_artists = row['count']
            elif row['type'] == 'band':
                total_bands = row['count']
            elif row['type'] == 'non-professional':
                total_non_professional = row['count']

        # Calculate percentages for types
        if total_musicians > 0:
            percentage_artists = round((total_artists / total_musicians) * 100, 2)
            percentage_bands = round((total_bands / total_musicians) * 100, 2)
            percentage_non_professional = round((total_non_professional / total_musicians) * 100, 2)
        else:
            percentage_artists = 0
            percentage_bands = 0
            percentage_non_professional = 0

        # Get gender counts for Artists and Non-Professionals only
        cursor.execute("""
            SELECT
                SUM(CASE WHEN gender = 'male' AND type IN ('artist', 'non-professional') THEN 1 ELSE 0 END) AS male_count,
                SUM(CASE WHEN gender = 'female' AND type IN ('artist', 'non-professional') THEN 1 ELSE 0 END) AS female_count,
                SUM(CASE WHEN gender = 'other' AND type IN ('artist', 'non-professional') THEN 1 ELSE 0 END) AS other_count,
                SUM(CASE WHEN (gender IS NULL OR gender = '') AND type IN ('artist', 'non-professional') THEN 1 ELSE 0 END) AS unknown_count
            FROM musicians
        """)
        gender_counts = cursor.fetchone()

        male_count = gender_counts['male_count']
        female_count = gender_counts['female_count']
        other_count = gender_counts['other_count']
        unknown_count = gender_counts['unknown_count']

        # Calculate gender percentages based on total number of Artists and Non-Professionals
        total_relevant_musicians = male_count + female_count + other_count + unknown_count

        if total_relevant_musicians > 0:
            male_percentage = round((male_count / total_relevant_musicians) * 100, 2)
            female_percentage = round((female_count / total_relevant_musicians) * 100, 2)
            other_percentage = round((other_count / total_relevant_musicians) * 100, 2)
            unknown_percentage = round((unknown_count / total_relevant_musicians) * 100, 2)
        else:
            male_percentage = 0
            female_percentage = 0
            other_percentage = 0
            unknown_percentage = 0

        # New query to get the count of profiles considered "ready"
        cursor.execute("""
            SELECT COUNT(*) AS ready_profiles
            FROM musicians
            WHERE (genre IS NOT NULL OR cover_image IS NOT NULL OR bio IS NOT NULL)
        """)
        ready_profiles = cursor.fetchone()['ready_profiles']

        cursor.close()

        return render_template(
            'a/dashboard.html',
            username=session['username'],
            total_artists=total_artists,
            total_bands=total_bands,
            total_non_professional=total_non_professional,
            percentage_artists=percentage_artists,
            percentage_bands=percentage_bands,
            percentage_non_professional=percentage_non_professional,
            male_count=male_count,
            female_count=female_count,
            other_count=other_count,
            unknown_count=unknown_count,
            male_percentage=male_percentage,
            female_percentage=female_percentage,
            other_percentage=other_percentage,
            unknown_percentage=unknown_percentage,
            total_count=total_musicians,
            ready_profiles=ready_profiles  # Pass ready profiles count to template
        )

    return redirect(url_for('login'))


@app.route('/listartists', methods=['GET'])
def listartists():
    if 'loggedin' in session:
        connection = mysql.connect  # Use the correct method to get the connection
        cursor = connection.cursor(MySQLdb.cursors.DictCursor)

        search_query = request.args.get('search', '').strip()  # Get the search query from the URL parameters
        letter = request.args.get('letter', '').strip().upper()  # Get the letter parameter from the URL

        # Handle '0-9' case
        if letter == '0-9':
          letter = '0-9'
        elif len(letter) != 1 or not (letter.isalpha() or letter == '0'):
          letter = ''  # Default to empty if invalid
          
        # Get current page number from request args, default to 1
        page = int(request.args.get('page', 1))
        items_per_page = 20
        
        # Calculate offset and limit
        offset = (page - 1) * items_per_page
        
        # Build the query based on the presence of search query and letter filter
        if search_query:
            if letter == '0-9':
                cursor.execute("""
                    SELECT musician_id AS id, musicians_english AS name, type, gender, remarks, birth_date, death_date, bio, cover_image
                    FROM musicians
                    WHERE musicians_english REGEXP '^[0-9]' AND musicians_english LIKE %s
                    ORDER BY musicians_english
                    LIMIT %s OFFSET %s
                """, (f'%{search_query}%', items_per_page, offset))
            elif letter:
                cursor.execute("""
                    SELECT musician_id AS id, musicians_english AS name, type, gender, remarks, birth_date, death_date, bio, cover_image
                    FROM musicians
                    WHERE musicians_english LIKE %s AND musicians_english LIKE %s
                    ORDER BY musicians_english
                    LIMIT %s OFFSET %s
                """, (f'%{search_query}%', f'{letter}%', items_per_page, offset))
            else:
                cursor.execute("""
                    SELECT musician_id AS id, musicians_english AS name, type, gender, remarks, birth_date, death_date, bio, cover_image
                    FROM musicians
                    WHERE musicians_english LIKE %s
                    ORDER BY musicians_english
                    LIMIT %s OFFSET %s
                """, (f'%{search_query}%', items_per_page, offset))
        else:
            if letter == '0-9':
                cursor.execute("""
                    SELECT musician_id AS id, musicians_english AS name, type, gender, remarks, birth_date, death_date, bio, cover_image
                    FROM musicians
                    WHERE musicians_english REGEXP '^[0-9]'
                    ORDER BY musicians_english
                    LIMIT %s OFFSET %s
                """, (items_per_page, offset))
            elif letter:
                cursor.execute("""
                    SELECT musician_id AS id, musicians_english AS name, type, gender, remarks, birth_date, death_date, bio, cover_image
                    FROM musicians
                    WHERE musicians_english LIKE %s
                    ORDER BY musicians_english
                    LIMIT %s OFFSET %s
                """, (f'{letter}%', items_per_page, offset))
            else:
                cursor.execute("""
                    SELECT musician_id AS id, musicians_english AS name, type, gender, remarks, birth_date, death_date, bio, cover_image
                    FROM musicians
                    ORDER BY musicians_english
                    LIMIT %s OFFSET %s
                """, (items_per_page, offset))

        musicians = cursor.fetchall()

        # Ensure fetched data is a list
        if isinstance(musicians, tuple):
            musicians = list(musicians)

        # Add encoded_name to each musician dictionary
        for musician in musicians:
            musician['encoded_name'] = musician['name'].replace(' ', '-').lower()

            # Determine if the profile is complete
            musician['profile_complete'] = all([
                musician.get('birth_date'),
                musician.get('death_date'),
                musician.get('deathplace'),
                # musician.get('bio'),
                # musician.get('cover_image')
            ])

        # Calculate total number of pages
        if search_query:
            if letter == '0-9':
                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM musicians
                    WHERE musicians_english REGEXP '^[0-9]' AND musicians_english LIKE %s
                """, (f'%{search_query}%',))
            elif letter:
                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM musicians
                    WHERE musicians_english LIKE %s AND musicians_english LIKE %s
                """, (f'%{search_query}%', f'{letter}%'))
            else:
                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM musicians
                    WHERE musicians_english LIKE %s
                """, (f'%{search_query}%',))
        else:
            if letter == '0-9':
                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM musicians
                    WHERE musicians_english REGEXP '^[0-9]'
                """)
            elif letter:
                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM musicians
                    WHERE musicians_english LIKE %s
                """, (f'{letter}%',))
            else:
                cursor.execute("""
                    SELECT COUNT(*) AS total
                    FROM musicians
                """)

        total_items = cursor.fetchone()['total']
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        cursor.close()
        
        return render_template(
            'a/listartists.html',
            musicians=musicians,
            page=page,
            total_pages=total_pages,
            active_page='listartists',
            profile_type="musician",
            letter=letter
        )
    
    return redirect(url_for('login'))


@app.route('/addartists', methods=['GET', 'POST'])
def addartists():
    if 'loggedin' not in session:
        return redirect(url_for('login'))

    print("Entering addartists function")  # Debugging entry point

    connection = mysql.connect
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)


    # Fetch the list of artists for the dropdown
    cursor.execute("SELECT musician_id AS id, musicians_english AS name, type FROM musicians")
    musicians = cursor.fetchall()

    try:
        if request.method == 'POST': 
            # Extract form data
            musician_name_en = request.form.get('name_en')
            musician_name_np = request.form.get('name_np')
            musician_type = request.form.get('type')
            gender = request.form.get('gender')
            gender_other = request.form.get('gender_other')
            remarks = request.form.get('remarks')

            print(f'Form data: name_en={musician_name_en}, name_np={musician_name_np}, type={musician_type}, gender={gender}, gender_other={gender_other}, remarks={remarks}')  # Debugging form data

            if gender == 'other':
                gender = gender_other

            # Validate required fields
            if not all([musician_name_en, musician_name_np, musician_type]):
                flash('All required fields must be filled out.', 'error')
                return redirect(url_for('addartists'))

            # Insert new artist
            cursor.execute("""
                INSERT INTO musicians (musicians_english, musicians_nepali, type, gender, remarks)
                VALUES (%s, %s, %s, %s, %s)
            """, (musician_name_en, musician_name_np, musician_type, gender, remarks))
            musician_id = cursor.lastrowid
            connection.commit()
            print(f'New artist added with ID: {musician_id}')  # Debugging new artist ID
            
            # Handle file upload
            cover_image = None
            profile_image = None

            if 'cover_image' in request.files:
                file = request.files['cover_image']
                if file and file.filename:
                   artist_name_sanitized = musician_name_en.replace(" ", "-").lower()
                   new_filename = f"{artist_name_sanitized}-cover-{musician_id}.jpg"
                   image_path = os.path.join('static/images', new_filename)
                   file.save(image_path)
                   cover_image = new_filename

            if 'profile_image' in request.files:
                file = request.files['profile_image']
                if file and file.filename:
                   artist_name_sanitized = musician_name_en.replace(" ", "-").lower()
                   new_filename = f"{artist_name_sanitized}-profile-{musician_id}.jpg"
                   image_path = os.path.join('static/images', new_filename)
                   file.save(image_path)
                   profile_image = new_filename
                   
            # Handle other form fields
            bio = request.form.get('bio')
            genre = request.form.getlist('genre')
            # discography = request.form.get('discography')
            # awards = request.form.getlist('awards[]')
            website = request.form.get('website')
            facebook = request.form.get('facebook')
            twitter = request.form.get('twitter')
            instagram = request.form.get('instagram')
            youtube = request.form.get('youtube')
            spotify = request.form.get('spotify')
            apple_music = request.form.get('apple_music')
            soundcloud = request.form.get('soundcloud')
            # noodle = request.form.get('noodle')
            player_embed = request.form.get('player_embed')

            # awards_str = ','.join(awards) if awards else ''
            genre_str = ','.join(genre) if genre else ''

            birth_date = request.form.get('birth_date') or None
            # birthplace = request.form.get('birthplace') or None
            death_date = request.form.get('death_date') or None
            # deathplace = request.form.get('deathplace') or None

            print(f'Musician Type: {musician_type}')

            if musician_type == 'band':
                band_members_ids = request.form.getlist('band_members[][musician_id]')
                band_members_positions = request.form.getlist('band_members[][position]')
                band_members_active = request.form.getlist('band_members[][active]')

                # Debugging output
                print(f'Band Members IDs: {band_members_ids}')
                print(f'Band Members Positions: {band_members_positions}')
                print(f'Band Members Active: {band_members_active}')

                if len(band_members_ids) != len(band_members_positions) or len(band_members_ids) != len(band_members_active):
                    # This can occur if the active checkboxes are not filled, adjust accordingly
                    # Assume all unchecked checkboxes are 'inactive'
                    band_members_active = ['0'] * len(band_members_ids)

                cursor.execute('''
                    UPDATE musicians
                    SET bio = %s, profile_image = %s, cover_image = %s, genre = %s, website = %s, facebook = %s, 
                        twitter = %s, instagram = %s, youtube = %s, spotify = %s, apple_music = %s, soundcloud = %s,
                        player_embed = %s, birth_date = %s, death_date = %s
                    WHERE musician_id = %s
                ''', (bio, profile_image, cover_image, genre_str, website, facebook, twitter, instagram,
                      youtube, spotify, apple_music, soundcloud, player_embed, birth_date, death_date, musician_id))

                cursor.execute('DELETE FROM bandmembers WHERE band_id = %s', (musician_id,))

                for i in range(len(band_members_ids)):
                    active = 1 if band_members_active[i] == 'on' else 0
                    cursor.execute('''
                        INSERT INTO bandmembers (band_id, musician_id, position, active)
                        VALUES (%s, %s, %s, %s)
                    ''', (musician_id, band_members_ids[i], band_members_positions[i], active))

                # Debugging confirmation
                print(f'Band members for band ID {musician_id} updated successfully.')

            elif musician_type == 'artist':
                featured_artists_ids = request.form.getlist('featured_artists[][musician_id]')
                featured_artists_roles = request.form.getlist('featured_artists[][role]')
                featured_artists_active = request.form.getlist('featured_artists[][active]')

                # Debugging output
                print(f'Featured Artists IDs: {featured_artists_ids}')
                print(f'Featured Artists Roles: {featured_artists_roles}')
                print(f'Featured Artists Active: {featured_artists_active}')

                if len(featured_artists_ids) != len(featured_artists_roles) or len(featured_artists_ids) != len(featured_artists_active):
                    raise ValueError("Mismatch in the number of featured artists' data fields")

                cursor.execute('''
                    UPDATE musicians
                    SET bio = %s, profile_image = %s, cover_image = %s, genre = %s, website = %s, facebook = %s, 
                        twitter = %s, instagram = %s, youtube = %s, spotify = %s, apple_music = %s, soundcloud = %s, 
                        player_embed = %s, birth_date = %s, death_date = %s
                    WHERE musician_id = %s
                ''', (bio, profile_image, cover_image, genre_str, website, facebook, twitter, instagram,
                      youtube, spotify, apple_music, soundcloud, player_embed, birth_date, death_date, musician_id))

                cursor.execute('DELETE FROM bandmembers WHERE artist_id = %s', (musician_id,))

                for i in range(len(featured_artists_ids)):
                    active = 1 if featured_artists_active[i] == 'on' else 0
                    cursor.execute('''
                        INSERT INTO bandmembers (band_id, musician_id, position, active)
                        VALUES (%s, %s, %s, %s)
                    ''', (musician_id, band_members_ids[i], band_members_positions[i], active))

                # Debugging confirmation
                print(f'Featured artists for artist ID {musician_id} updated successfully.')

            connection.commit()
            flash('Artist updated successfully!', 'success')
            return redirect(url_for('dashboard'))
          
        # Render the add artist page if the request method is GET and no ID is provided
        return render_template('a/addartists.html', musicians=musicians)

    except MySQLdb.Error as e:
        print(f'An error occurred: {e}')
        flash(f'An error occurred: {e}', 'error')
        return redirect(url_for('addartists'))  # Ensure there's a return in case of error

    finally:
        cursor.close()
        connection.close()




@app.route('/editmusician/<int:id>', methods=['GET', 'POST'])
def edit_musician(id):
    if 'loggedin' in session:
        connection = mysql.connect
        cursor = connection.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            type_ = request.form.get('type')
            name_en = request.form.get('name_en')
            name_np = request.form.get('name_np')
            gender = request.form.get('gender')
            gender_other = request.form.get('gender_other') if request.form.get('gender') == 'other' else None
            remarks = request.form.get('remarks')

            # Update musician details
            cursor.execute("""
                UPDATE musicians
                SET type = %s, musicians_english = %s, musicians_nepali = %s, gender = %s, gender_other = %s, remarks = %s
                WHERE musician_id = %s
            """, (type_, name_en, name_np, gender, gender_other, remarks, id))
            connection.commit()

            flash('Artist details updated successfully!', 'success')  # Set flash message

            cursor.close()
            return redirect(url_for('dashboard'))  # Redirect to dashboard or any other page

        # Get musician details
        cursor.execute("""
            SELECT musician_id AS id, musicians_english AS name_en, musicians_nepali AS name_np, type, gender, gender_other, remarks
            FROM musicians
            WHERE musician_id = %s
        """, (id,))
        musician = cursor.fetchone()
        cursor.close()

        if musician:
            return render_template('a/editmusician.html', musician=musician)
        else:
            return "Musician not found", 404

    return redirect(url_for('login'))


@app.route('/<int:id>/<artist_name>')
def artistprofile(id, artist_name):
    connection = mysql.connect
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)

    try:
        # Fetch the musician profile based on the musician id
        cursor.execute('SELECT * FROM musicians WHERE musician_id = %s', (id,))
        profile = cursor.fetchone()
        print("Fetched Profile:", profile)  # For debugging

        if profile:
            # Verify if the artist name in the URL matches the one in the database
            db_artist_name = profile['musicians_english'].replace(' ', '-').lower()
            url_artist_name = artist_name.replace(' ', '-').lower()

            if db_artist_name != url_artist_name:
                flash('Profile not found', 'danger')
                return redirect(url_for('listartists'))

            # Extract details
            facebook = profile.get('facebook', '')
            twitter = profile.get('twitter', '')
            instagram = profile.get('instagram', '')
            youtube = profile.get('youtube', '')
            spotify = profile.get('spotify', '')
            apple_music = profile.get('apple_music', '')
            soundcloud = profile.get('soundcloud', '')
            awards = profile.get('awards', '')
            player_embed = profile.get('player_embed', '')
            cover_image = profile.get('cover_image', '')
            musician_type = profile.get('type', '')  # Fetch the type from the database

            # Fetch the discography for the musician
            cursor.execute('''
                SELECT collection_title, image, compilation FROM collection
                WHERE musician_id = %s
            ''', (id,))
            discography = cursor.fetchall()
            print("Fetched Discography:", discography)  # For debugging

            band_members = []
            featured_bands = []
            related_musicians = []  # Initialize related_musicians

            # Fetch band members if the musician is a band
            if musician_type == 'band':
                cursor.execute('''
                    SELECT bm.*, m.musicians_english AS musician_name
                    FROM bandmembers bm 
                    JOIN musicians m ON bm.musician_id = m.musician_id 
                    WHERE bm.band_id = %s
                ''', (id,))
                band_members = cursor.fetchall()

                # Fetch related musicians who are also part of the band
                cursor.execute('''
                    SELECT DISTINCT m.* 
                    FROM bandmembers bm
                    JOIN musicians m ON m.musician_id = bm.musician_id
                    WHERE bm.band_id = %s
                ''', (id,))
                related_musicians = cursor.fetchall()

            # Fetch bands the musician is a part of if it's an artist
            if musician_type == 'artist':
                cursor.execute('''
                    SELECT bm.band_id, m.musicians_english AS band_name 
                    FROM bandmembers bm 
                    JOIN musicians m ON bm.band_id = m.musician_id 
                    WHERE bm.musician_id = %s
                ''', (id,))
                featured_bands = cursor.fetchall()

                # Fetch all bands the artist is featured in
                cursor.execute('''
                    SELECT DISTINCT bm.band_id, b.musicians_english AS band_name
                    FROM bandmembers bm
                    JOIN musicians b ON bm.band_id = b.musician_id
                    WHERE bm.musician_id = %s
                ''', (id,))
                related_bands = cursor.fetchall()

            # Fetch related musicians
            cursor.execute('''
                SELECT DISTINCT m.* 
                FROM bandmembers bm
                JOIN musicians m ON (m.musician_id = bm.musician_id OR m.musician_id = bm.band_id)
                WHERE bm.musician_id = %s OR bm.band_id = %s
            ''', (id, id))
            
            related_musicians += cursor.fetchall()
            
            cursor.close()

            return render_template(
                'a/artistprofile.html',
                profile=profile,
                discography=discography,  # Pass the discography data to the template
                awards=awards,
                facebook=facebook,
                twitter=twitter,
                instagram=instagram,
                youtube=youtube,
                spotify=spotify,
                apple_music=apple_music,
                soundcloud=soundcloud,
                player_embed=player_embed,
                cover_image=cover_image,
                musician_id=id,
                musician_type=musician_type,  # Pass the type to the template
                band_members=band_members,  # Pass band members to the template
                featured_bands=featured_bands,  # Pass featured bands to the template
                related_musicians=related_musicians  # Pass related musicians to the template
            )
        else:
            flash('Profile not found', 'danger')
            return redirect(url_for('listartists'))
    except Exception as e:
        print("Error:", str(e))
        flash('An error occurred', 'danger')
        return redirect(url_for('listartists'))



@app.route('/editprofile/<int:profile_id>', methods=['GET', 'POST'])
def edit_profile(profile_id):
    connection = mysql.connect
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Fetch all musicians for the dropdown
    cursor.execute("SELECT musician_id AS id, musicians_english AS name, type FROM musicians")
    musicians = cursor.fetchall()

    if isinstance(musicians, tuple):
        musicians = list(musicians)
    
    musicians.sort(key=lambda x: x['name'].strip().lower())

    if request.method == 'GET':
        # Fetch the musician's current data
        cursor.execute("SELECT musician_id AS id, musicians_english AS name, type, gender, remarks, birth_date, birthplace, death_date, bio, cover_image, genre, discography, awards, website, facebook, twitter, instagram, youtube, spotify, apple_music, soundcloud, noodle, player_embed FROM musicians WHERE musician_id = %s", (profile_id,))
        musician = cursor.fetchone()

        if not musician:
            cursor.close()
            return "Musician not found", 404

        # Fetch band members if type is 'band'
        band_members = []
        if musician['type'] == 'band':
            cursor.execute("SELECT bandmember_id, musician_id, position, active FROM bandmembers WHERE band_id = %s", (profile_id,))
            band_members = cursor.fetchall()

        # Convert 'None' to empty list or default value if needed
        musician['discography'] = musician['discography'] or []
        musician['genre'] = musician['genre'] or []
        musician['awards'] = musician['awards'] or []

        # Render the template with musician, musicians, and band members data
        cursor.close()
        return render_template('a/editprofile.html', musician=musician, musicians=musicians, band_members=band_members)

    elif request.method == 'POST':
        
        # Handle form submission for editing the musician's profile
        musician_id = profile_id
        birth_date = request.form.get('birth_date') or None
        birthplace = request.form.get('birthplace')
        death_date = request.form.get('death_date') or None
        deathplace = request.form.get('deathplace')
        bio = request.form.get('bio')
        cover_image = None

        if 'cover_image' in request.files:
            file = request.files['cover_image']
            if file and file.filename:
                artist_name_sanitized = request.form.get('artist_name', '').replace(" ", "-").lower()
                new_filename = f"{profile_id}-{artist_name_sanitized}.jpg"
                image_path = os.path.join('static/images', new_filename)
                file.save(image_path)
                cover_image = new_filename

        genre = request.form.getlist('genre')
        discography = request.form.getlist('discography[]')
        awards = request.form.getlist('awards[]')
        website = request.form.get('website')
        facebook = request.form.get('facebook')
        twitter = request.form.get('twitter')
        instagram = request.form.get('instagram')
        youtube = request.form.get('youtube')
        spotify = request.form.get('spotify')
        apple_music = request.form.get('apple_music')
        soundcloud = request.form.get('soundcloud')
        noodle = request.form.get('noodle')
        player_embed = request.form.get('player_embed')

        # Convert lists to comma-separated strings for storage
        genre_str = ','.join(genre)
        discography_str = ','.join(discography)
        awards_str = ','.join(awards)

        # Update musician record
        update_query = """
        UPDATE musicians SET 
            birth_date = %s, birthplace = %s, death_date = %s, deathplace = %s, bio = %s, cover_image = %s, genre = %s, discography = %s, awards = %s, 
            website = %s, facebook = %s, twitter = %s, instagram = %s, youtube = %s, 
            spotify = %s, apple_music = %s, soundcloud = %s, noodle = %s, player_embed = %s 
        WHERE musician_id = %s
        """
        cursor.execute(update_query, (
            birth_date, birthplace, death_date, deathplace, bio, cover_image, genre_str, discography_str, awards_str, website, facebook, 
            twitter, instagram, youtube, spotify, apple_music, soundcloud, noodle, player_embed, musician_id
        ))

        # Handle band members updates
        if musician['type'] == 'band':
            # Delete existing band members
            cursor.execute("DELETE FROM bandmembers WHERE band_id = %s", (profile_id,))
            
            # Insert updated band members
            band_member_data = []
            for index in range(len(request.form.getlist('band_members[][musician_id]'))):
                musician_id = request.form.get(f'band_members[{index}][musician_id]')
                position = request.form.get(f'band_members[{index}][position]')
                active = request.form.get(f'band_members[{index}][active]') == 'on'
                if musician_id:
                    band_member_data.append((profile_id, musician_id, position, active))
            
            cursor.executemany("INSERT INTO bandmembers (band_id, musician_id, position, active) VALUES (%s, %s, %s, %s)", band_member_data)
        
        connection.commit()
        cursor.close()

        # Flash a success message
        flash('Profile updated successfully!', 'success')

        return redirect(url_for('dashboard', profile_id=profile_id))

    # Default return in case the request method is not 'GET' or 'POST'
    cursor.close()
    return "Invalid request method", 400




@app.route('/search', methods=['GET'])
def search():
    if 'loggedin' in session:
        query = request.args.get('query', '')

        # Establish MySQL connection
        connection = mysql.connect
        cursor = connection.cursor()

        # Search in the musicians table
        cursor.execute("""
            SELECT musician_id, musicians_english AS full_name, type, cover_image 
            FROM musicians 
            WHERE musicians_english LIKE %s
            UNION
            SELECT musician_id, musicians_nepali AS full_name, type, cover_image 
            FROM musicians 
            WHERE musicians_nepali LIKE %s
        """, ('%' + query + '%', '%' + query + '%'))

        musicians = cursor.fetchall()
        cursor.close()

        # Convert tuples to dictionaries
        musicians_list = [
            {'musician_id': m[0], 'full_name': m[1], 'type': m[2], 'cover_image': m[3]}
            for m in musicians
        ]

        # Redirect to listmusicians page with search results
        return render_template('a/listartists.html', musicians=musicians_list, query=query)
    return redirect(url_for('login'))
@app.route('/roles')
def roles():
    # Check if user is logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))  # Redirect to login page if not logged in

    # Fetch roles from the database
    try:
        connection = mysql.connect
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM role')  # Adjust your table name if different
        roles = cursor.fetchall()

        # Debugging statements
        print("Fetched roles:", roles)

    except Exception as e:
        print("Error fetching roles:", e)
        roles = []

    return render_template('a/roles.html', roles=roles)


@app.route('/add_role', methods=['POST'])
def add_role():
    role_name = request.form.get('role')
    if not role_name:
        return jsonify({'success': False, 'message': 'Role name is required'})

    connection = mysql.connect
    cursor = connection.cursor()
    cursor.execute('INSERT INTO role (role) VALUES (%s)', (role_name,))
    connection.commit()
    role_id = cursor.lastrowid  # Get the new role's ID

    return jsonify({'success': True, 'role_id': role_id})

@app.route('/update_role', methods=['POST'])
def update_role():
    role_id = request.form['role_id']
    role_name = request.form['role_name']
    
    connection = mysql.connect
    cursor = connection.cursor()
    cursor.execute('UPDATE role SET role = %s WHERE role_id = %s', (role_name, role_id))
    connection.commit()
    
    return jsonify(success=True)


# Route to serve the template
@app.route('/test')
def test():
    return render_template('a/test.html')
# Route to handle form submission
@app.route('/submit-genders', methods=['POST'])
def submit_genders():
    # Extract data from the request
    data = request.json  # Assuming the data is sent as JSON
    genders = data.get('genders', [])
    
    # Process the data (e.g., save to a database)
    print('Submitted genders:', genders)
    
    # Example response
    return jsonify({'success': True, 'message': 'Genders submitted successfully'})


@app.route('/genders', methods=['GET'])
def get_genders():
    connection = mysql.connect
    cursor = connection.cursor()
    cursor.execute("SELECT gender FROM test")
    genders = cursor.fetchall()
    cursor.close()
    gender_list = [row[0] for row in genders]  # Convert tuple to list
    return jsonify(gender_list)

@app.route('/genders', methods=['POST'])
def add_gender():
    data = request.json
    new_gender = data.get('name')
    if new_gender:
        connection = mysql.connect
        cursor = connection.cursor()
        cursor.execute("INSERT INTO test (gender) VALUES (%s)", (new_gender,))
        connection.commit()
        cursor.close()
        return jsonify({'message': 'Gender added successfully!'}), 201
    return jsonify({'error': 'Invalid input'}), 400

@app.route('/genres')
def genres():
    # Check if user is logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))  # Redirect to login page if not logged in

    # Fetch genres from the database
    try:
        connection = mysql.connect
        cursor = connection.cursor()
        cursor.execute('SELECT id, name FROM genres')  # Adjusted to match your table structure
        genres = cursor.fetchall()

        # Debugging statements
        print("Fetched genres:", genres)

    except Exception as e:
        print("Error fetching genres:", e)
        genres = []

    return render_template('a/genres.html', genres=genres)


@app.route('/add_genre', methods=['POST'])
def add_genre():
    genre_name = request.form.get('genre')
    if not genre_name:
        return jsonify({'success': False, 'message': 'Genre name is required'})

    connection = mysql.connect
    cursor = connection.cursor()
    cursor.execute('INSERT INTO genres (name) VALUES (%s)', (genre_name,))
    connection.commit()
    genre_id = cursor.lastrowid  # Get the new genre's ID

    # Create a newOption object with the new genre details
    new_option = {'id': genre_id, 'name': genre_name}

    # Return the newOption object along with success
    return jsonify({'success': True, 'newOption': new_option})  # Ensure 'newOption' is returned

@app.route('/update_genre', methods=['POST'])
def update_genre():
    genre_id = request.form['genre_id']
    genre_name = request.form['genre_name']
    
    connection = mysql.connect
    cursor = connection.cursor()
    cursor.execute('UPDATE genres SET name = %s WHERE id = %s', (genre_name, genre_id))
    connection.commit()
    
    return jsonify(success=True)


# Route to fetch all genres
@app.route('/getgenres', methods=['GET'])
def get_genres():
    connection = mysql.connect
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    query = "SELECT id AS id, name AS name FROM genres ORDER BY name ASC"
    cursor.execute(query)
    genres = cursor.fetchall()
    cursor.close()
    
    return jsonify([{'id': genre['id'], 'name': genre['name']} for genre in genres])


@app.route('/languages')
def languages():
    # Check if user is logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))  # Redirect to login page if not logged in

    # Fetch languages from the database
    try:
        connection = mysql.connect
        cursor = connection.cursor()
        cursor.execute('SELECT id, name FROM languages')  # Adjusted to match your table structure
        languages = cursor.fetchall()

        # Debugging statements
        print("Fetched languages:", languages)

    except Exception as e:
        print("Error fetching languages:", e)
        languages = []

    return render_template('a/languages.html', languages=languages)


@app.route('/add_language', methods=['POST'])
def add_language():
    language_name = request.form.get('language')
    if not language_name:
        return jsonify({'success': False, 'message': 'Language name is required'})

    connection = mysql.connect
    cursor = connection.cursor()
    cursor.execute('INSERT INTO languages (name) VALUES (%s)', (language_name,))
    connection.commit()
    language_id = cursor.lastrowid  # Get the new language's ID

    # Create a newOption object with the new genre details
    new_option = {'id': language_id, 'name': language_name}

    # Return the newOption object along with success
    return jsonify({'success': True, 'newOption': new_option})  # Ensure 'newOption' is returned

@app.route('/update_language', methods=['POST'])
def update_language():
    language_id = request.form['language_id']
    language_name = request.form['language_name']
    
    connection = mysql.connect
    cursor = connection.cursor()
    cursor.execute('UPDATE languages SET name = %s WHERE id = %s', (language_name, language_id))
    connection.commit()
    
    return jsonify(success=True)

# Route to fetch all languages
@app.route('/getlanguages', methods=['GET'])
def get_languages():
    connection = mysql.connect
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    query = "SELECT id AS id, name AS name FROM languages ORDER BY name ASC"
    cursor.execute(query)
    languages = cursor.fetchall()
    cursor.close()

    return jsonify([{'id': language['id'], 'name': language['name']} for language in languages])


# Route to fetch all musicians
@app.route('/musicians', methods=['GET'])
def get_musicians():
    connection = mysql.connect
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    query = "SELECT musician_id AS id, musicians_english AS name FROM musicians ORDER BY musicians_english ASC"
    cursor.execute(query)
    musicians = cursor.fetchall()
    cursor.close()

    return jsonify([{'id': musician['id'], 'name': musician['name']} for musician in musicians])


# Change the route to match the desired page
@app.route('/collection')
def collection():
    connection = mysql.connect
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT id, tagname, title FROM collections")
    collections_data = cursor.fetchall()
    cursor.close()
    return render_template('a/collection.html', collections=collections_data)  # Serve the 'collection.html' page

# Change the route to match the desired page
@app.route('/addcollection')
def addcollection():
    return render_template('a/addcollection.html')  # Serve the 'collection.html' page

@app.route('/edit_collection/<int:collection_id>', methods=['GET', 'POST'])
def edit_collection(collection_id):
    connection = mysql.connect
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)

    try:
        if request.method == 'GET':
            print(f"Fetching collection details for collection ID: {collection_id}")
            cursor.execute("""  # Fetch the current data of the collection
                SELECT c.*, 
                       GROUP_CONCAT(ca.musician_id) AS musicians,
                       GROUP_CONCAT(cl.language_id) AS languages,
                       GROUP_CONCAT(cg.genre_id) AS genres
                FROM collections c
                LEFT JOIN collection_artists ca ON c.id = ca.collection_id
                LEFT JOIN collection_language cl ON c.id = cl.collection_id
                LEFT JOIN collection_genre cg ON c.id = cg.collection_id
                WHERE c.id = %s
            """, (collection_id,))
            collection_data = cursor.fetchone()

            # Debugging: Check if data was found
            print(f"Collection data: {collection_data}")

            # Parse selected IDs
            selected_genres = collection_data['genres'].split(',') if collection_data and collection_data['genres'] else []
            selected_languages = collection_data['languages'].split(',') if collection_data and collection_data['languages'] else []
            selected_artists = collection_data['musicians'].split(',') if collection_data and collection_data['musicians'] else []


            print(f"Selected Genres: {selected_genres}")
            print(f"Selected Languages: {selected_languages}")
            print(f"Selected Artists: {selected_artists}")

            # Fetch names for genres, languages, and artists
            genres, languages, artists = [], [], []
            if selected_genres:
                genre_ids = tuple(selected_genres) if len(selected_genres) > 1 else (selected_genres[0],) # Convert to tuple for IN clause
                cursor.execute("""SELECT id, name FROM genres WHERE id IN %s""", (genre_ids,))
                genres = cursor.fetchall()
                print(f"Fetched Genres: {genres}")

            if selected_languages:
                language_ids = tuple(selected_languages)
                cursor.execute("""SELECT id, name FROM languages WHERE id IN %s""", (language_ids,))
                languages = cursor.fetchall()
                print(f"Fetched Languages: {languages}")

            if selected_artists:
                artist_ids = tuple(selected_artists)
                cursor.execute("""SELECT musician_id, musicians_english FROM musicians WHERE musician_id IN %s""", (artist_ids,))
                artists = cursor.fetchall()
                print(f"Fetched Artists: {artists}")

            return render_template('a/editcollection.html', 
                                   collection=collection_data, 
                                   genres=genres, 
                                   languages=languages, 
                                   artists=artists,
                                   selected_genres=[{'id': g['id'], 'name': g['name']} for g in genres], 
                                   selected_languages=[{'id': l['id'], 'name': l['name']} for l in languages],
                                   selected_artists=[{'id': a['musician_id'], 'name': a['musicians_english']} for a in artists])

        if request.method == 'POST':
            print(f"Form submission for collection ID: {collection_id}")

            # Check all form data
            print("Form Data Keys:", request.form.keys())
            # Handle form submission logic
            new_genres = request.form.get('selected_genres', '')  # No need to default to '[]'
            new_languages = request.form.get('selected_languages', '')  # No need to default to '[]'
            new_artists = request.form.get('selected_artists', '')

            # Debugging: Log the raw form data
            print(f"Raw Genres: {new_genres}")
            print(f"Raw Languages: {new_languages}")
            print(f"Raw Artists: {new_artists}")

             # Split the comma-separated values into lists
            new_genres = new_genres.split(',') if new_genres else []
            new_languages = new_languages.split(',') if new_languages else []
            new_artists = new_artists.split(',') if new_artists else []

            print(f"New Genres: {new_genres}")
            print(f"New Languages: {new_languages}")
            print(f"New Artists: {new_artists}")

            # Delete existing associations for artists, languages, and genres
            cursor.execute("DELETE FROM collection_artists WHERE collection_id = %s", (collection_id,))
            cursor.execute("DELETE FROM collection_language WHERE collection_id = %s", (collection_id,))
            cursor.execute("DELETE FROM collection_genre WHERE collection_id = %s", (collection_id,))

            # Insert new associations
            for artist_id in new_artists:
                if artist_id:
                    cursor.execute("INSERT INTO collection_artists (collection_id, musician_id) VALUES (%s, %s)", (collection_id, artist_id))
                else:
                    print(f"Skipping invalid artist ID: {artist_id}")

            for language_id in new_languages:
                if language_id:
                    cursor.execute("INSERT INTO collection_language (collection_id, language_id) VALUES (%s, %s)", (collection_id, language_id))

            for genre_id in new_genres:
                if genre_id:
                   cursor.execute("INSERT INTO collection_genre (collection_id, genre_id) VALUES (%s, %s)", (collection_id, genre_id))

            connection.commit()
            print(f"Changes committed for collection {collection_id}")

            return redirect(url_for('edit_collection', collection_id=collection_id))  # Redirect after POST

    except Exception as e:
        print(f"Error occurred: {e}")
        connection.rollback()  # Rollback if something goes wrong
        flash("An error occurred while updating the collection. Please try again.")
        return render_template('a/editcollection.html', collection_id=collection_id)

    finally:
        cursor.close()  # Always close the cursor

@app.route('/submit-form', methods=['POST'])
def create_collection():
    title = request.json.get('title')
    tagname = request.json.get('tagname')
    genres = request.json.get('genre')  # List of genre names
    languages = request.json.get('language')  # List of language names
    musicians = request.json.get('artist')  # List of musician names

    print(f"Received data:  title={title}, tagname={tagname}, genres={genres}, languages={languages}, musicians={musicians}")

    try:
        # Start a transaction
        connection = mysql.connect
        cursor = connection.cursor(MySQLdb.cursors.DictCursor)
        
        print("Connection established, starting transaction.")

        # Create the collection
        cursor.execute("INSERT INTO collections (title, tagname) VALUES (%s, %s)", (title, tagname))
        connection.commit()
        collection_id = cursor.lastrowid  # Get the collection_id from the newly inserted row

        print(f"Collection created, collection_id={collection_id}")

        # Verify collection_id
        if not collection_id:
            print("Failed to create collection. Collection ID is invalid.")
            return jsonify({'error': 'Failed to create collection. Collection ID is funny.'}), 400

        # Insert genres
        print("Inserting genres...")
        for genre in genres:
            cursor.execute("SELECT id FROM genres WHERE name = %s", (genre,))
            genre_result = cursor.fetchone()
            
            if genre_result:  # Check if genre_result is not None
                genre_id = genre_result.get('id')  # Use .get() to safely access the id
                print(f"Inserting genre '{genre}' with genre_id={genre_id}")
                cursor.execute("INSERT INTO collection_genre (collection_id, genre_id) VALUES (%s, %s)", (collection_id, genre_id))
            else:
                print(f"Genre '{genre}' not found in the database.")

        # Insert languages
        print("Inserting languages...")
        for language in languages:
            cursor.execute("SELECT id FROM languages WHERE name = %s", (language,))
            language_result = cursor.fetchone()
            if language_result:
                language_id = language_result.get('id')
                print(f"Inserting language '{language}' with language_id={language_id}")
                cursor.execute("INSERT INTO collection_language (collection_id, language_id) VALUES (%s, %s)", (collection_id, language_id))
            else:
                print(f"Language '{language}' not found in the database.")

        # Insert musicians
        print("Inserting musicians...")
        for musician in musicians:
            cursor.execute("SELECT musician_id FROM musicians WHERE musicians_english = %s", (musician,))
            musician_result = cursor.fetchone()
            if musician_result:
                musician_id = musician_result.get('musician_id')
                print(f"Inserting musician '{musician}' with musician_id={musician_id}")
                cursor.execute("INSERT INTO collection_artists (collection_id, musician_id) VALUES (%s, %s)", (collection_id, musician_id))
            else:
                print(f"Musician '{musician}' not found in the database.")

        connection.commit()  # Commit all changes in the transaction
        print("Transaction committed successfully.")
        cursor.close()

        # Redirect the user to the collection page after success
        print("Redirecting to collection page.")
        collection_url = url_for('collection')  # This generates the URL for the collection route
        return jsonify({'message': 'Form submitted successfully!', 'redirect_url': collection_url})

    except Exception as e:
        import traceback
        print(f"Error details: {traceback.format_exc()}")  # Log the full error stack trace
        return jsonify({'error': 'Failed to create collection and add data'}), 500


@app.route('/logout')
def logout():
     session.clear()
     return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
