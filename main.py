import sqlite3
from calendar import month

from flask import (Flask,
                   render_template,
                   request,
                   redirect,
                   url_for)
from werkzeug.security import (generate_password_hash,
                               check_password_hash)
from flask_login import (LoginManager,
                         UserMixin,
                         login_user,
                         logout_user,
                         login_required,
                         current_user)
import datetime

app = Flask(__name__)
app.secret_key = "bot15"

connection = sqlite3.connect("blogposts.db")
cursor = connection.cursor()

login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    connection = sqlite3.connect("blogposts.db")
    cursor = connection.cursor()

    user = cursor.execute(
        'SELECT * FROM user WHERE id = ?', user_id).fetchone()
    if user is not None:
        return User(user[0], user[1], user[2])
    return None

def close_db(connection = None):
    if connection is not None:
        connection.close()

@app.teardown_appcontext
def close_connection(exception):
    close_db()

@app.route("/")
def home_page():
    connection = sqlite3.connect("blogposts.db")
    cursor = connection.cursor()

    cursor.execute('''
        SELECT
            blogs.id,
            blogs.title,
            blogs.content,
            blogs.author_id,
            user.username,
            COUNT(like.id) AS likes
        FROM 
            blogs
        JOIN 
            user ON blogs.author_id = user.id
        LEFT JOIN 
            like ON blogs.id = like.post_id
        GROUP 
            BY blogs.id, blogs.title, blogs.content, blogs.author_id, user.username
    ''')

    cursor.execute("SELECT * FROM blogs JOIN user ON blogs.author_id = user.id")
    result = cursor.fetchall()
    posts = []
    for post in reversed(result):
        cursor.execute("SELECT COUNT(*) FROM like WHERE post_id = ?", (post[0],))
        likes_count = cursor.fetchone()[0]

        posts.append(
            {"id": post[0],
             "title": post[1],
             "content": post[2],
             "author_id": post[3],
             "time": post[4],
             "username": post[6],
             "likes": likes_count
             }
        )
        if current_user.is_authenticated:
            cursor.execute('SELECT post_id FROM like WHERE user_id = ?', (current_user.id, ))
            likes_result = cursor.fetchall()
            liked_posts = []
            for like in likes_result:
                liked_posts.append(like[0])
            posts[-1]["liked_posts"] = liked_posts

    context = {"posts": posts}
    return render_template("blog.html", **context)

@app.route("/add/", methods=["GET", "POST"])
@login_required
def add_post():
    connection = sqlite3.connect("blogposts.db")
    cursor = connection.cursor()
    right_now = datetime.datetime.now()

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        right_now = datetime.datetime.now()
        time = f"{right_now.date().day}/{right_now.date().month}/{right_now.date().year}"
        cursor.execute(
            "INSERT INTO blogs (title, content, author_id, time) VALUES (?, ?, ?, ?)",
            (title, content, current_user.id, time)
        )
        connection.commit()
        return redirect(url_for("home_page"))
    time = f"{right_now.date().day}/{right_now.date().month}/{right_now.date().year}"
    return render_template("add_post.html", time=time)

@app.route("/post/<post_id>")
def post(post_id):
    connection = sqlite3.connect("blogposts.db")
    cursor = connection.cursor()

    result = cursor.execute(
        "SELECT * FROM blogs WHERE id = ?", (post_id,)
    ).fetchone()
    post_dict = {"id":result[0], "title":result[1], "content": result[2]}
    return render_template("post.html", post = post_dict)

@app.route("/register/", methods=["GET", "POST"])
def register():
    connection = sqlite3.connect("blogposts.db")
    cursor = connection.cursor()

    if request.method == "POST":
        email = request.form["email"]
        username = request.form["username"]
        password = request.form["password"]
        try:
            cursor.execute(
                "INSERT INTO user (username, password_hash, email) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), email)
            )
            connection.commit()
            print("Action Successful")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            return render_template("registration.html",
                                   message="Email or Username already in use")
    return render_template("registration.html")

@app.route("/login/", methods=["GET", "POST"])
def login():
    connection = sqlite3.connect("blogposts.db")
    cursor = connection.cursor()

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = cursor.execute(
            "SELECT * FROM user WHERE username = ?",
            (username,)
        ).fetchone()
        if user and User(user[0], user[1], user[2]).check_password(password):
            login_user(User(user[0], user[1], user[2]))
            print(current_user.id)
            return redirect(url_for("home_page"))
        else:
            return render_template("login.html",
                                   message="Invalid username or password")
    return render_template("login.html")

@app.route("/logout/")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home_page"))

@app.route("/delete/(<int:post_id>)", methods=["POST"])
@login_required
def delete_post(post_id):
    connection = sqlite3.connect("blogposts.db")
    cursor = connection.cursor()

    post = cursor.execute('SELECT * FROM blogs WHERE id = ?',
                          (post_id,)).fetchone()
    if post and post[3] == current_user.id:
        cursor.execute('DELETE FROM blogs WHERE id = ?', (post_id,))
        connection.commit()  # commit the deletion
        connection.close()
        print("Post deleted")
    else:
        connection.close()
        print("Unauthorized delete attempt or post not found")

    return redirect(url_for("home_page"))

def user_is_liking(user_id, post_id):
    connection = sqlite3.connect("blogposts.db")
    cursor = connection.cursor()

    like = cursor.execute(
        'SELECT * FROM like WHERE user_id = ? AND post_id = ?',
        (user_id, post_id)).fetchone()
    return bool(like)

@app.route('/like/<int:post_id>')
@login_required
def like_post(post_id):
    connection = sqlite3.connect("blogposts.db")
    cursor = connection.cursor()

    post = cursor.execute('SELECT * FROM blogs WHERE id = ?',
                          (post_id,)).fetchone()
    if post:
        if user_is_liking(current_user.id, post_id):
            cursor.execute('DELETE FROM like WHERE user_id = ? AND post_id = ?',
                           (current_user.id, post_id))
            connection.commit()
            print("you unliked this post")
        else:
            cursor.execute('INSERT INTO like (user_id, post_id) VALUES (?,?)',
                           (current_user.id, post_id))
            connection.commit()
            print("you liked this post")
        return redirect(url_for("home_page"))
    return "Post not found", 404

if __name__=="__main__":
    app.run()