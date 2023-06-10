import os
import requests
import urllib.parse
from functools import wraps
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, url_for, request, session
from flask_socketio import join_room, leave_room, send, SocketIO
from flask_session import Session
import random
from string import ascii_uppercase
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
import datetime

# API KEY: export API_KEY=pk_06bfd2c6157948b2a9751c1e2bcc1f69
# Configure application
app = Flask(__name__)


# Configure session to use filesystem (instead of signed cookies)
app.config["SECRET_KEY"] = "halkhflakshfl"
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.environ.get("SESSION_FILE_DIR", "Digital Minds/project/flask_session")
Session(app)

socketio = SocketIO(app)

rooms = {}

currently_works = ""

def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)

        if code not in rooms:
            break

    return code


def apology(message, code=400):
    """Render message as an apology to user."""
    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s
    return render_template("apology.html", top=code, bottom=escape(message)), code


def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/1.1.x/patterns/viewdecorators/
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function


def lookup(symbol):
    """Look up quote for symbol."""

    # Contact API
    try:
        api_key = os.environ.get("API_KEY")
        url = f"https://cloud.iexapis.com/stable/stock/{urllib.parse.quote_plus(symbol)}/quote?token={api_key}"
        response = requests.get(url)
        response.raise_for_status()
    except requests.RequestException:
        return None

    # Parse response
    try:
        quote = response.json()
        return {
            "name": quote["companyName"],
            "price": float(quote["latestPrice"]),
            "symbol": quote["symbol"]
        }
    except (KeyError, TypeError, ValueError):
        return None


def usd(value):
    """Format value as USD."""
    return f"${value:,.2f}"


# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///project.db")
redirect("/")

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show and access invites"""
    if request.method == "GET":
        if "user_id" in session:
            # Retrieve user information from the database based on the session user_id
            user_id = session["user_id"]

            rows = db.execute("SELECT registery FROM users WHERE id = ?", user_id)
            if len(rows) == 0:
                return redirect("/login")

            registery = rows[0]["registery"]

            if registery == 1:
                return redirect("/edit")

            else:
                user_id = session["user_id"]
                invites_db = db.execute(
                    "SELECT * FROM invites WHERE reciever_id = ? ORDER BY date DESC", user_id
                )
                return render_template("index.html", database=invites_db)
        else:
            return redirect("/login")
    else:
        code = request.form.get("code")
        delete = request.form.get("delete")
        bcode = request.form.get("bcode", False)
        bdelete = request.form.get("bdelete", False)
        if bcode != False:
            status = "Opened"
            db.execute("UPDATE invites SET status = ? WHERE room = ?", status, code)
            return redirect(url_for("chat", fcode=code))
        if bdelete != False:
            db.execute("DELETE FROM invites WHERE room = ?", delete)
        return redirect("/")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")

    else:
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("Username Required")
        if not password:
            return apology("Password Required")
        if not confirmation:
            return apology("Confirmation Requried")
        if password != confirmation:
            return apology("PASSWORDS DO NOT MATCH")

        hash = generate_password_hash(password)
        one = 1

        try:
            new_user = db.execute(
                "INSERT INTO users (username, hash, registery) VALUES (?, ?, ?)",
                username,
                hash,
                one,
            )
        except:
            return apology("Username Already Exists")

        session["user_id"] = new_user

        return redirect("/edit")


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        user_id = session["user_id"]

        rows = db.execute("SELECT hash FROM users WHERE id = ?", user_id)
        current_password_hash = rows[0]["hash"]

        if not check_password_hash(current_password_hash, request.form.get("old")):
            return apology("Current Password Is Incorrect", 403)

        new = request.form.get("new")
        confirmation = request.form.get("confirmation")
        if not new or new != confirmation:
            return apology("New passwords do not match", 400)

        new_password_hash = generate_password_hash(new)
        db.execute("UPDATE users SET hash = ? WHERE id = ?", new_password_hash, user_id)

        flash("Password Canged Successfully!")

        return redirect("/")

    else:
        return render_template("change_password.html")


@app.route("/find", methods=["GET", "POST"])
@login_required
def find():
    """Find Friends"""
    if request.method == "GET":
        if "user_id" in session:
            # Retrieve user information from the database based on the session user_id
            user_id = session["user_id"]

            rows = db.execute("SELECT registery FROM users WHERE id = ?", user_id)
            registery = rows[0]["registery"]

            if registery == 1:
                return redirect("/edit")

            else:
                return render_template("find.html")
        else:
            return redirect("/login")
    else:
        user_id = session["user_id"]
        rows = db.execute("SELECT username FROM users WHERE id = ?", user_id)
        current_username = rows[0]["username"]
        fusername = request.form.get("username")

        if not fusername:
            return apology("Username Required")
        else:
            rows = db.execute("SELECT username FROM users WHERE id = ?", user_id)
            current_username = rows[0]["username"]
            if current_username == fusername:
                return apology("You Can't Search Yourself")

            rows = db.execute("SELECT * FROM users WHERE username = ?", fusername)
            if len(rows) != 1:
                return apology("This User Doesn't Exist")

            return redirect(url_for("friend", fusername=fusername))


@app.route("/friend", methods=["GET", "POST"])
@login_required
def friend():
    """Show Profile of User"""
    if request.method == "POST":
        id = session["user_id"]
        fusername = request.form.get("fusername")
        rows = db.execute("SELECT id FROM users WHERE username = ?", fusername)
        user_id = rows[0]["id"]
        rows = db.execute("SELECT friends, friend_names FROM users WHERE id = ?", id)
        user_friends = rows[0]["friends"]
        friend_names = rows[0]["friend_names"]
        fn = str(fusername) + ","
        fid = str(user_id) + ","
        if user_friends is None:
            db.execute(
                "UPDATE users SET friends = ?, friend_names = ? WHERE id = ?",
                fid,
                fn,
                id,
            )
            flash("Friend Added!")
            return redirect(url_for("friend", fusername=fusername))
        if fid in user_friends:
            return redirect(url_for("chat", fusername=fusername))
        else:
            updated = user_friends + fid
            updatedfn = friend_names + fn
            db.execute(
                "UPDATE users SET friends = ?, friend_names = ? WHERE id = ?",
                updated,
                updatedfn,
                id,
            )
            flash("Friend Added!")
            return redirect(url_for("friend", fusername=fusername))
    else:
        if "user_id" in session:
            # Retrieve user information from the database based on the session user_id
            user_id = session["user_id"]

            rows = db.execute("SELECT registery FROM users WHERE id = ?", user_id)
            registery = rows[0]["registery"]

            if registery == 1:
                return redirect("/edit")

            else:
                id = session["user_id"]
                fusername = request.args.get("fusername")
                rows = db.execute(
                    "SELECT name, age, gender, bio, id FROM users WHERE username = ?",
                    fusername,
                )
                name = rows[0]["name"]
                age = rows[0]["age"]
                gender = rows[0]["gender"]
                bio = rows[0]["bio"]
                user_id = rows[0]["id"]

                rows = db.execute("SELECT friends FROM users WHERE id = ?", id)
                user_friends = rows[0]["friends"]
                fid = str(user_id) + ","
                if user_friends is None:
                    button = "Add Friend"
                else:
                    if fid in user_friends:
                        button = "Message Friend"
                    else:
                        button = "Add Friend"
                return render_template(
                    "fprofile.html",
                    username=fusername,
                    name=name,
                    age=age,
                    gender=gender,
                    bio=bio,
                    button=button,
                )

        else:
            return redirect("/login")


@app.route("/edit", methods=["GET", "POST"])
def edit():
    """Edit profile"""
    if request.method == "GET":
        if "user_id" in session:
            # Retrieve user information from the database based on the session user_id
            user_id = session["user_id"]
            rows = db.execute(
                "SELECT registery, username FROM users WHERE id = ?", user_id
            )
            registery = rows[0]["registery"]
            username = rows[0]["username"]

            if registery != 2:
                return render_template("edit.html", username=username)

            else:
                rows = db.execute(
                    "SELECT username, name, age, bio FROM users WHERE id = ?", user_id
                )
                username = rows[0]["username"]
                name = rows[0]["name"]
                age = rows[0]["age"]
                bio = rows[0]["bio"]

                return render_template(
                    "edit.html", username=username, name=name, age=age, bio=bio
                )

        else:
            return redirect("/login")
    else:
        name = request.form.get("name")
        age = request.form.get("age")
        gender = request.form.get("gender")
        bio = request.form.get("bio")

        if not name:
            return apology("Name Required")
        if "," in name:
            return apology("Invalid Name")
        if not age:
            return apology("Age Required")
        if not gender:
            return apology("Gender Required")
        if not bio:
            return apology("Bio Required")

        user_id = session["user_id"]
        rows = db.execute("SELECT registery, username FROM users WHERE id = ?", user_id)
        registery = rows[0]["registery"]
        username = rows[0]["username"]

        if registery == 1:
            two = 2
            db.execute("UPDATE users SET registery = ? WHERE id = ?", two, user_id)

        db.execute(
            "UPDATE users SET name = ?, age = ?, gender = ?, bio = ? WHERE id = ?",
            name,
            age,
            gender,
            bio,
            user_id,
        )

        return redirect("/profile")


@app.route("/leave", methods=["POST"])
@login_required
def leave():
    """Leave Chat Room"""
    user_id = session["user_id"]
    db.execute("UPDATE users SET room = NULL WHERE id = ?", user_id)
    return redirect(url_for("chat"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Find Friends"""
    if request.method == "GET":
        if "user_id" in session:
            # Retrieve user information from the database based on the session user_id
            user_id = session["user_id"]

            rows = db.execute("SELECT registery FROM users WHERE id = ?", user_id)
            registery = rows[0]["registery"]

            if registery != 2:
                return redirect("/edit")

            else:
                rows = db.execute(
                    "SELECT username, name, age, gender, bio FROM users WHERE id = ?",
                    user_id,
                )
                username = rows[0]["username"]
                name = rows[0]["name"]
                age = rows[0]["age"]
                bio = rows[0]["bio"]
                gender = rows[0]["gender"]

                return render_template(
                    "profile.html",
                    username=username,
                    name=name,
                    age=age,
                    bio=bio,
                    gender=gender,
                )

        else:
            return redirect("/login")

    else:
        return redirect("/edit")


@app.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    if request.method == "POST":
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)
        invite = request.form.get("invite", False)

        if invite != False:
            f = request.form.get("f")

            if f is None or f == "":
                return apology("Friend Is Required")
            else:
                room = generate_unique_code(4)
                session["room"] = room
                print(room)
                rooms[room] = {"members": 0, "messages": []}
                user_id = session["user_id"]
                db.execute("UPDATE users SET room = ? WHERE id = ?", room, user_id)
                user_id = session["user_id"]
                rows = db.execute("SELECT name FROM users WHERE id = ?", user_id)
                sender_name = rows[0]["name"]
                rows = db.execute("SELECT id FROM users WHERE username = ?", f)
                reciever_id = rows[0]["id"]
                sender_id = user_id
                status = "Unopened"
                date = datetime.datetime.now()
                message = (
                    str(sender_name)
                    + " has invited you to a chat room! Use the room code: "
                    + str(room)
                    + " to join or click on it directly over here -->"
                )
                db.execute(
                    "INSERT INTO invites (message, sender_id, reciever_id, room, date, status, sender_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    message,
                    sender_id,
                    reciever_id,
                    room,
                    date,
                    status,
                    sender_name,
                )
                flash(f + " was invited to the Room!")
                return redirect(url_for("room"))

        if join != False and not code:
            return apology("Room Code Required to Join Room")

        room = code.upper()
        if create != False:
            room = generate_unique_code(4)
            print(room)
            rooms[room] = {"members": 0, "messages": []}
        elif code not in rooms:
            return apology("Room Does Not Exist")
        session["room"] = room
        user_id = session["user_id"]
        db.execute("UPDATE users SET room = ? WHERE id = ?", room, user_id)

        return redirect(url_for("room"))
    else:
        if "user_id" in session:
            # Retrieve user information from the database based on the session user_id
            user_id = session["user_id"]

            rows = db.execute("SELECT registery, room FROM users WHERE id = ?", user_id)
            registery = rows[0]["registery"]
            room = rows[0]["room"]

            if registery == 1:
                return redirect("/edit")

            else:
                fcode = request.args.get("fcode")
                if fcode is not None:
                    code = fcode
                user_id = session["user_id"]
                rows = db.execute(
                    "SELECT name, friend_names FROM users WHERE id = ?", user_id
                )
                name = rows[0]["name"]
                friend_names = rows[0]["friend_names"]

                if friend_names is None:
                    friend_names = ","

                friend_names = friend_names.split(",")

                fusername = request.args.get("fusername")

                if fusername is not None:
                    return render_template(
                        "home.html",
                        name=name,
                        friend_names=friend_names,
                        fusername=fusername,
                    )
                else:
                    fusername = None
                    if fcode is not None:
                        code = fcode
                        return render_template("home.html", name=name, friend_names=friend_names, fusername=fusername, code=code)
                    else:
                        return render_template("home.html", name=name, friend_names=friend_names, fusername=fusername)
        else:
            return redirect("/login")


@app.route("/room", methods=["GET", "POST"])
@login_required
def room():
    if "user_id" in session:
        # Retrieve user information from the database based on the session user_id
        user_id = session["user_id"]

        rows = db.execute("SELECT registery FROM users WHERE id = ?", user_id)
        registery = rows[0]["registery"]

        if registery == 1:
            return redirect("/edit")

        else:
            user_id = session["user_id"]
            rows = db.execute("SELECT name, room FROM users WHERE id = ?", user_id)
            room = rows[0]["room"]
            if not room or room not in rooms:
                return redirect(url_for("chat"))
            else:
                return render_template("room.html", room=room)
    else:
        return redirect("/login")


@socketio.on("message")
def message(data):
    if "user_id" in session:
        # Retrieve user information from the database based on the session user_id
        user_id = session["user_id"]

        rows = db.execute(
            "SELECT registery, room, name FROM users WHERE id = ?", user_id
        )
        registery = rows[0]["registery"]

        if registery == 1:
            return redirect("/edit")

        else:
            name = rows[0]["name"]
            room = rows[0]["room"]
            if room not in rooms:
                return apology("Something Went Wrong, Please Try Again")

            content = {"name": name, "message": data["data"]}
            send(content, to=room)
            rooms[room]["messages"].append(content)
            print(f"{name} said: {data['data']})")

    else:
        return redirect("/login")


@socketio.on("connect")
def connect(auth):
    user_id = session["user_id"]
    rows = db.execute("SELECT room, name FROM users WHERE id = ?", user_id)
    room = rows[0]["room"]
    name = rows[0]["name"]

    if not room:
        return apology("Something Went Wrong, Please Try Again")
    if room not in rooms:
        leave_room(room)
        return apology("Something Went Wrong, Please Try Again")

    join_room(room)
    send({"name": name, "message": "has entered the room"}, to=room)
    rooms[room]["members"] += 1
    print(f"{name} joined room {room}")


@socketio.on("disconnect")
def disconnect():
    user_id = session["user_id"]
    rows = db.execute("SELECT name, room FROM users WHERE id = ?", user_id)
    room = rows[0]["room"]
    name = rows[0]["name"]
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]
            db.execute("UPDATE users SET room = NULL WHERE id = ?", user_id)
            return redirect("/chat")

    send({"name": name, "message": "has left the room"}, to=room)
    print(f"{name} has left the room {room}")

    if __name__ == "__main__":
        app.run(host="0.0.0.0",  port=5000)
        socketio.run(app, debug=True)
        redirect("/")




