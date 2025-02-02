from flask import Flask, render_template, request, session, url_for, redirect
import requests
from bs4 import BeautifulSoup
import nltk
nltk.download('all')
from nltk.tokenize import word_tokenize, sent_tokenize
from nltk.corpus import stopwords
from nltk.probability import FreqDist
import json
from urllib.parse import urlparse
from textblob import TextBlob
from summa.summarizer import summarize
import psycopg2
from google_auth_oauthlib.flow import Flow
import os
import google.auth.transport.requests
from google.oauth2 import id_token
import google
from flask_session import Session  # Import Flask-Session


################################################################################################################


# Connecting the postgres database
conn = psycopg2.connect("postgresql://deepu:EzaXdzYTSLL2Xo2I6nIy1FESO08L1CSk@dpg-cu4jed5ds78s739uqkn0-a/news_records")
# Create a cursor object
cur = conn.cursor()

create_table_query = """
CREATE TABLE IF NOT EXISTS news_data (
    s_no SERIAL PRIMARY KEY,
    url TEXT,
    headline TEXT,
    article TEXT,
    summary TEXT,
    words INTEGER,
    sentances INTEGER,
    stop_words INTEGER,
    pos_tag TEXT,
    sentiment_score REAL,
    sentiment_label VARCHAR(20),
    keywords TEXT,
    email VARCHAR(255) NOT NULL
);
"""

# Execute the SQL query
cur.execute(create_table_query)

# Define the SQL query to create the table
create_table_query = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255),
    profile TEXT
);
"""

# Execute the SQL query
cur.execute(create_table_query)

# Commit the transaction
conn.commit()


# Define the text analysis function that takes a piece of text as input
def text_analysis(text):
    # Tokenize the text into words and sentences
    word_list = word_tokenize(text)
    sent_list = sent_tokenize(text)
    
    # Count the number of sentences
    sent_count = len(sent_list)
    
    # Define a list of punctuation marks
    punct = [".", "?", "!"]
    
    # Remove punctuation marks from the word list
    n = len(word_list)
    word_list = [word for word in word_list if word not in punct]
    
    # Count the number of words after removing punctuationS
    word_count = len(word_list)

    # Perform Part-of-Speech (POS) tagging on the word list
    pos_list = nltk.pos_tag(word_list, tagset="universal")
    
    # Create a dictionary to store the counts of different POS tags
    pos_dict = {}
    for i in pos_list:
        if i[1] not in pos_dict:
            pos_dict[i[1]] = 1
        else:
            pos_dict[i[1]] += 1
    
    # Convert the POS dictionary to JSON format
    pos_json = json.dumps(pos_dict)
    
    # Get English stopwords from NLTK corpus
    stop_word = nltk.corpus.stopwords.words("english")
    
    # Count the number of stopwords in the word list
    stop_count = 0
    for i in word_list:
        if i in stop_word:
            stop_count += 1

    # Return a dictionary containing various text analysis metrics
    return {
        "Word_count": word_count,
        "Sentance_Count": sent_count,
        "Post_INFO": pos_json,
        "Stop_Words": stop_count,
    }


# Define the sentiment analysis function that takes a news article as input
def sentiment_analysis(news_article):
    # Perform sentiment analysis using TextBlob
    blob = TextBlob(news_article)
    
    # Calculate the sentiment polarity score of the news article
    sentiment_score = blob.sentiment.polarity

    # Determine sentiment polarity based on the sentiment score
    if sentiment_score > 0:
        sentiment_label = 'positive'
    elif sentiment_score < 0:
        sentiment_label = 'negative'
    else:
        sentiment_label = 'neutral'
    
    # Return the sentiment score and sentiment label
    return round(sentiment_score,5), sentiment_label




# Define the keyword extraction function that takes a piece of text as input
def keyword(text):
    # Tokenize the text into words
    tokens = word_tokenize(text)
    
    # Convert all words to lowercase and filter out non-alphanumeric tokens
    tokens = [word.lower() for word in tokens if word.isalnum()]
    
    # Retrieve a set of English stopwords from NLTK's stopwords corpus
    stop_words = set(stopwords.words('english'))
    
    # Create a new list containing only those tokens that are not present in the set of stopwords
    filtered_tokens = [word for word in tokens if word not in stop_words]

    # Compute the frequency distribution of words in the filtered_tokens list
    fdist = FreqDist(filtered_tokens)
    
    # Extract the most common 5 words (adjustable) from the frequency distribution
    keywords = fdist.most_common(5)

    # Return the extracted keywords
    return keywords



#####################################################################################################################3


# Initialize Flask application
app = Flask(__name__)

app.secret_key = 'hello'



# Path to the client secrets file
client_secrets_file = "credential.json"

app.config['SESSION_TYPE'] = 'filesystem'
Session(app)
scopes = ['https://www.googleapis.com/auth/userinfo.profile',
          'https://www.googleapis.com/auth/userinfo.email',
          'openid']

# Redirect URI for the OAuth flow
redirect_uri = 'https://new-extractor-web-app.onrender.com/callback'

# Create the OAuth flow object
flow = Flow.from_client_secrets_file(client_secrets_file, scopes=scopes, redirect_uri=redirect_uri)

@app.route('/login')
def login():

    # Using "global" to change login variable inside the function.
    global login
    
    # Checking does user alreday?
    if 'google_token' in session:
        login = True
        # User is already authenticated, redirect to a protected route
        return redirect(url_for('home'))
    else:
        # User is not authenticated, redirect to Google OAuth flow
        authorization_url, _ = flow.authorization_url(prompt='consent')
        return redirect(authorization_url)

#

@app.route('/callback')
def callback():
    # Get the parameters from the request URL
    state = request.args.get('state')
    prompt = request.args.get('prompt')
    client_id = request.args.get('client_id')
    scope = request.args.get('scope')

    # Handle the callback from the Google OAuth flow
    flow.fetch_token(code=request.args.get('code'))
    session['google_token'] = flow.credentials.token

    # Redirect to the protected route 
    return redirect(url_for('protected'))




@app.route('/protected')
def protected():

    # Using "global" to change login variable inside the function.
    global login

    # Checking does user authenticated?
    if 'google_token' in session:
        login = True
        # User is authenticated, retrieve user information
        session_credentials = flow.credentials
        session['google_token'] = session_credentials.token
        session['google_refresh_token'] = session_credentials.refresh_token
        session['google_client_id'] = session_credentials.client_id
        session['google_client_secret'] = session_credentials.client_secret
        session['google_scopes'] = session_credentials.scopes
        
        # Extract user profile information
        userinfo_endpoint = 'https://www.googleapis.com/oauth2/v2/userinfo'
        headers = {'Authorization': f'Bearer {session["google_token"]}'}
        userinfo_response = requests.get(userinfo_endpoint, headers=headers)
        userinfo_data = userinfo_response.json()

        # Make email and profile global, to use outside the function
        global email
        global profile

        # Extracting user email and profile photo
        email = userinfo_data.get('email')
        profile = userinfo_data.get('picture')  
        
        # Fecthing user email from our user data, to check if user already exist or not!
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cur.fetchone()

        # User already exists, do not insert into the database
        if not existing_user:
            
            try:
                # inserting user into the database
                cur.execute("INSERT INTO users (email, profile) VALUES (%s, %s)", (email, profile))
                conn.commit()
                print("User inserted into the database")
            except Exception as e:
                conn.commit()
                return render_template("result.html", result={"error": str(e),"mag":" try again after some time and report the developer at[deepak.kumar176362@gmail.com]"})
        
       
        # Redirecting to Home Page.
        return redirect(url_for('home'))
    else:
        # User is not authenticated, redirect to the login page again.
        return redirect(url_for('login'))
    
@app.route('/logout')
def logout():
    # Clear the session
    session.clear()
    global login
    global email
    global profile
    email=''
    profile=''
    login = False
    return redirect(url_for('home'))

# Defining global variable to use
login = False
free = 0
profile = ""
email = ""

# Defining the admins
admins = ["deepak.kumar176362@gmail.com","deepaksingh987171@gmail.com","su-23008@sitare.org","kushal@sitare.org",'atmabodha@gmail.com']



# Defining the home page route
@app.route("/", methods=["POST", "GET"])
def home():

    global login

    # Checking if user is already login or not.
    if session:
        login = True
    
    # Check if the request method is POST
    if request.method == "POST":

        # checking does user login or not 
        if 'google_token' not in session:
            global free

            # user is not login we are giving 2 chances to use this with some restricted details.
            if free < 2 :
                free += 1
                url = request.form.get("URL")
                if url:
                    try:
                        # Check if the input is a valid URL
                        result = urlparse(url)
                        if all([result.scheme, result.netloc]):
                            # Fetch the HTML content of the URL
                            page = requests.get(url)
                            soup = BeautifulSoup(page.content, "html.parser")
                            # Extract header and content from the HTML using BeautifulSoup
                            header = soup.find(class_='HNMDR')
                            content = soup.find(class_="_s30J clearfix")
                            
                            if content:
                                # Extract text from header and content tags
                                extracted_head = header.get_text(separator='\n', strip=True)
                                extracted_text = content.get_text(separator="\n", strip=True)
                            if not content:
                                a = soup.find(class_='JYT7F')
                                b = a.get_text(separator='\n',strip=True).split("Source:\nTOI.in")
                                extracted_head = b[0]
                                extracted_text = b[1]

                            if extracted_head and extracted_text:

                                # defining dictionary to saved the result 
                                analysis_result ={}

                                # saving the headline and the article in the resulting dictionary
                                analysis_result["Extracted_head"] = extracted_head
                                analysis_result["Extracted_Text"] = extracted_text

                                # remaining the data will not be calculated without login, hence setting other parameter to "Login first" 
                                analysis_result["Extracted_Date"] = "login to see"
                                analysis_result['Summary'] = "Login  first"
                                analysis_result['Sentiment_score'],analysis_result['Sentiment_label'] = "Login first","Login first"
                                analysis_result['Keywords'] = "Login first"

                                
                                return render_template("result.html", result=analysis_result)
                            else:
                                # Render an error message if content is not found
                                return render_template("result.html", result={"error": "Content not found"})
                        else:
                            # Render an error message if the URL is invalid
                            return render_template("result.html", result={"error": "Invalid URL"})
                    except Exception as e:
                        # Render an error message if an exception occurs during processing
                        return render_template("result.html", result={"error": str(e)})
                else:
                    # Render an error message if URL is not provided
                    return render_template("result.html", result={"error": "URL not provided"})
                        


            else:
                # User is not authenticated, redirect to a google login page 
                return redirect(url_for('login'))
        
        
        # Get the URL from the form form tag
        url = request.form.get("URL")
        if url:
            try:
                # Check if the input is a valid URL
                result = urlparse(url)
                if all([result.scheme, result.netloc]):
                    # Fetch the HTML content of the URL
                    page = requests.get(url)
                    soup = BeautifulSoup(page.content, "html.parser")
                    # Extract header and content from the HTML using BeautifulSoup
                    header = soup.find(class_='HNMDR')
                    content = soup.find(class_="_s30J clearfix")
                    
                    if content:
                        # Extract text from header, content tags and post date. 
                        extracted_head = header.get_text(separator='\n', strip=True)
                        extracted_text = content.get_text(separator="\n", strip=True)
                        extracted_date = soup.find(class_="xf8Pm byline").get_text(separator='\n',strip=True).split("Updated:")[1]
                    
                    # if content not found in above class than finding in different class
                    if not content:
                        a = soup.find(class_='JYT7F')
                        b = a.get_text(separator='\n',strip=True).split("Source:\nTOI.in")
                        extracted_head = b[0]
                        extracted_text = b[1]
                        extracted_date = soup.find(class_="C85PU").get_text(separator='\n',strip=True)

                    if extracted_head and extracted_text:
                        # Perform text analysis on the extracted text
                        analysis_result = text_analysis(extracted_text)
                        # Add additional analysis results like summary, sentiment analysis, and keywords
                        analysis_result["Extracted_head"] = extracted_head
                        analysis_result["Extracted_Text"] = extracted_text
                        analysis_result["Extracted_Date"] = extracted_date
                        analysis_result['Summary'] = summarize(extracted_text, ratio=0.2)
                        analysis_result['Sentiment_score'],analysis_result['Sentiment_label'] = sentiment_analysis(extracted_text)
                        analysis_result['Keywords'] = keyword(extracted_text)

                        
                        try:

                            #inserting the detailed data into the postgres database
                            cur.execute('''
                                INSERT INTO news_data(URL, headline, article, summary, words, sentances, stop_words, pos_tag, sentiment_score, sentiment_label, keywords, email)
                                VALUES (%s, %s, %s, %s,%s,%s,%s,%s,%s,%s,%s,%s)
                                        ''', (url,extracted_head,extracted_text,analysis_result['Summary'],analysis_result['Word_count'],analysis_result['Sentance_Count'],analysis_result['Stop_Words'],analysis_result['Post_INFO'],
                                            analysis_result['Sentiment_score'],analysis_result['Sentiment_label'],analysis_result['Keywords'],email))
                            
                            # commiting the changes
                            conn.commit()
                        except:
                            # if error comes in the transction than commiting and displaying the error
                            conn.commit()
                            return render_template("result.html", result={"error": str(e),"mag":" try again after some time and reporter the developer at[deepak.kumar176362@gmail.com]"})

                        # Render the result.html template with the analysis results
                        return render_template("result.html", result=analysis_result)
                    else:
                        # Render an error message if content is not found
                        return render_template("result.html", result={"error": "Content not found"})
                else:
                    # Render an error message if the URL is invalid
                    return render_template("result.html", result={"error": "Invalid URL"})
            except Exception as e:
                # Render an error message if an exception occurs during processing
                return render_template("result.html", result={"error": str(e),"mag":" try again after some time and reporter the developer at[deepak.kumar176362@gmail.com]"})
        else:
            # Render an error message if URL is not provided
            return render_template("result.html", result={"error": "URL not provided"})
    # Render the index.html template for GET requests
    return render_template("index.html",login=login,profile_photo = profile,email=email,admins=admins)


    



# Route for admin functionality
@app.route("/admin", methods=["GET", "POST"])
def admin():
    # Check if the email is in the list of admins
    if email in admins:
        # Execute SQL query to fetch all news data
        cur.execute("SELECT * FROM news_data")
        data1 = cur.fetchall()
        # Render admin.html template with the fetched data
        return render_template("admin.html", data=data1)
    else:
        # Render result.html template with an error message
        return render_template("result.html", result={"error": "You are not authorized"})

# Route for viewing user history
@app.route("/history", methods=["GET", "POST"])
def view_history():
    # Check if the email is available
    if email:
        # Execute SQL query to fetch news data for the logged-in user
        cur.execute("SELECT * FROM news_data WHERE email = %s", (email,))
        data1 = cur.fetchall()
        # Render view_history.html template with the fetched data
        return render_template("view_history.html", data=data1)
    else:
        # Render result.html template with an error message
        return render_template("result.html", result={"error": "Login first to see your history"})

# Route for displaying user details
@app.route("/user_details", methods=["GET", "POST"])
def user_details():
    # Check if the email is in the list of admins
    if email in admins:
        # Execute SQL query to fetch all user details
        cur.execute("SELECT * FROM users")
        data1 = cur.fetchall()
        # Render user_details.html template with the fetched data
        return render_template("user_details.html", data=data1)
    else:
        # Render result.html template with an error message
        return render_template("result.html", result={"error": "You are not authorized"})

# Route for developer page
@app.route("/developer", methods=["GET", "POST"])
def developer():
    # Render developer.html template
    return render_template("developer.html")




# Run the Flask application if this script is executed directly
if __name__ == "__main__":
    app.run(debug=True)
