import bcrypt
from flask import Flask, request, render_template, request, session
import pickle
import requests
import pandas as pd
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, flash
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import random
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

movies = pickle.load(open('./model/movies_list.pkl', 'rb'))
similarity = pickle.load(open('./model/similarity.pkl', 'rb'))

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)
app.secret_key = 'al&*5T2Ga)'

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    movie_id = db.Column(db.Integer)
    rating = db.Column(db.Integer)

    def __init__(self, user_id, movie_id, rating):
        self.user_id = user_id
        self.movie_id = movie_id
        self.rating = rating


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))

    def __init__(self, email, password, name):
        self.name = name
        self.email = email
        self.password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password):
        return bcrypt.checkpw(password.encode('utf-8'), self.password.encode('utf-8'))


with app.app_context():
    db.create_all()

@app.route('/signup', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        new_user = User(name=name, email=email, password=password)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/signin')

    return render_template('signup.html')


@app.route('/signin', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session['email'] = user.email
            session['name'] = user.name
            return redirect('/user-recommendation')
        else:
            flash('Invalid user. Please check your email and password.', 'error')
            return render_template('signin.html', error='Invalid user')

    return render_template('signin.html')

@app.route('/logout')
def logout():
    session.pop('email', None)
    return redirect('/signin')


@app.route('/save_rating', methods=['POST'])
def save_rating():
    if 'email' in session:
        user_email = session['email']
        user = User.query.filter_by(email=user_email).first()
        if user:
            movie_id = request.form.get('movie_id')
            rating_value = request.form.get('rating')

            # Check if a rating record already exists for this user and movie
            existing_rating = Rating.query.filter_by(user_id=user.id, movie_id=movie_id).first()

            if existing_rating:
                # Update the existing rating
                existing_rating.rating = rating_value
            else:
                # Create a new rating record
                rating = Rating(user_id=user.id, movie_id=movie_id, rating=rating_value)
                db.session.add(rating)

            db.session.commit()
            # flash('Rating saved successfully!', 'success')
        else:
            flash('Invalid user. Please check your email and password.', 'error')
    return redirect('/')


def fetch_poster(movie_id):
    url = "https://api.themoviedb.org/3/movie/{}?api_key=8265bd1679663a7ea12ac168da84d2e8&language=en-US".format(movie_id)
    data = requests.get(url)
    data = data.json()
    poster_path = data['poster_path']
    full_path = "https://image.tmdb.org/t/p/w500/" + poster_path
    return full_path

def recommend(movie):
    index = movies[movies['title'] == movie].index[0]
    distances = sorted(list(enumerate(similarity[index])), reverse= True, key=lambda x: x[1])
    recommended_movies_name = []
    recommended_movies_poster = []
    recommended_movies_id = []
    for i in distances[1:7]:
        movie_id = movies.iloc[i[0]].movie_id
        recommended_movies_poster.append(fetch_poster(movie_id))
        recommended_movies_name.append(movies.iloc[i[0]].title)
        recommended_movies_id.append(movie_id)

    return recommended_movies_name, recommended_movies_poster, recommended_movies_id

@app.route('/', methods = ['GET', 'POST'])
def recommendation():
    movie_list = movies['title'].values
    status = False
    if request.method == "POST":
        try:
            if request.form:
                movies_name = request.form['movies']
                print(movies_name)
                recommended_movies_name, recommended_movies_poster, recommended_movies_id = recommend(movies_name)
                print(recommended_movies_name)
                print(recommended_movies_poster)
                print(recommended_movies_id)
                status = True

                return render_template("prediction.html", movies_name = recommended_movies_name, poster = recommended_movies_poster, movies_id = recommended_movies_id, movie_list = movie_list, status = status)

        except Exception as e:
            error = {'error': e}
            return render_template("prediction.html",error = error, movie_list = movie_list, status = status)

    elif 'email' in session:
        return redirect('/user-recommendation')
    else:
        total_movies = len(movies)
        random_indices = random.sample(range(total_movies), 6)
        recommended_movies_poster = []
        recommended_movies_name = []
        recommended_movies_id = []
        for i in random_indices:
            movie_id = movies.iloc[i].movie_id
            recommended_movies_poster.append(fetch_poster(movie_id))
            recommended_movies_name.append(movies.iloc[i].title)
            recommended_movies_id.append(movie_id)
        #return render_template("prediction.html", movie_list = movie_list, status = status)
        return render_template("prediction.html", movies_name=recommended_movies_name, poster=recommended_movies_poster, movies_id = recommended_movies_id,
                               movie_list=movie_list, status=False)


def calculate_similarity(user1_id, user2_id):
    # Get ratings for movies rated by both users
    user1_ratings = Rating.query.filter_by(user_id=user1_id).all()
    user2_ratings = Rating.query.filter_by(user_id=user2_id).all()

    common_movie_ids = set(rating.movie_id for rating in user1_ratings).intersection(
        set(rating.movie_id for rating in user2_ratings)
    )

    if not common_movie_ids:
        return 0.0  # Users have no movies in common

    user1_vector = []
    user2_vector = []

    for movie_id in common_movie_ids:
        user1_rating = next((rating for rating in user1_ratings if rating.movie_id == movie_id), None)
        user2_rating = next((rating for rating in user2_ratings if rating.movie_id == movie_id), None)

        if user1_rating and user2_rating:
            user1_vector.append(user1_rating.rating)
            user2_vector.append(user2_rating.rating)

    # Calculate cosine similarity
    if user1_vector and user2_vector:
        user1_vector = np.array(user1_vector).reshape(1, -1)
        user2_vector = np.array(user2_vector).reshape(1, -1)
        similarity = cosine_similarity(user1_vector, user2_vector)
        return similarity[0][0]

    return 0.0

@app.route('/user-recommendation', methods = ['GET', 'POST'])
def user_based_recommendation():
    user = User.query.filter_by(email=session['email']).first()
    user_id = int(user.id)
    num_recommendations = 6
    user_ratings = Rating.query.filter_by(user_id=user_id).all()
    movie_list = movies['title'].values

    user_ratings_dict = {rating.movie_id: rating.rating for rating in user_ratings}
    rated_movie_ids = list(user_ratings_dict.keys())
    #index = movies[movies['title'] == movie].index[0]
    #all_movie_ids = [movie['movie_id'] for movie in movies]
    print('all')
    all_movie_ids = movies['movie_id']
    #all_movie_ids = [int (movie['movie_id']) for movie in movies]
    print(all_movie_ids[0:10])

    unrated_movie_ids = list(set(all_movie_ids) - set(rated_movie_ids))
    print('unrated_movie_ids')
    print(unrated_movie_ids[0:10])
    recommendation_scores = defaultdict(float)
    for movie_id in unrated_movie_ids:
        ratings_for_movie = Rating.query.filter_by(movie_id=movie_id).all()
        print('Rating table')
        print(ratings_for_movie)
        total_score = 0.0
        total_weight = 0.0

        for rating in ratings_for_movie:
            other_user_id = rating.user_id
            other_user_rating = rating.rating
            similarity_score = calculate_similarity(user_id,
                                                    other_user_id)  # Implement your similarity calculation method
            total_score += other_user_rating * similarity_score
            total_weight += similarity_score

        if total_weight > 0:
            recommendation_scores[movie_id] = total_score / total_weight

    recommended_movies_id = sorted(recommendation_scores, key=recommendation_scores.get, reverse=True)
    recommended_movies_name = []
    recommended_movies_poster = []
    print('length of recommended_movies_id:')
    print(recommended_movies_id)
    for movie_id in recommended_movies_id:
        #movie = next((m for m in movies if m['movie_id'] == movie_id), None)
        movie = movies[movies['movie_id'] == movie_id].values.flatten().tolist()
        if movie is not None:
            #recommended_movies_name.append(movie['title'])
            recommended_movies_name.append(movie[1])
            print(movie[1])
            #print(movie['title'])
            recommended_movies_poster.append(fetch_poster(movie_id))


    return render_template("prediction.html", movies_name=recommended_movies_name, poster=recommended_movies_poster,
                           movies_id=recommended_movies_id,
                           movie_list=movie_list, status=False)



if __name__ == '__main__':
    app.debug = True
    app.run()