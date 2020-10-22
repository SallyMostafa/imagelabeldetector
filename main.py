import logging
import os
import google.cloud.storage as storage
from google.cloud import datastore
from google.cloud import vision
from flask import Flask, request, render_template
import datetime

app = Flask(__name__)

# Configure this environment variable via app.yaml
GCS_IMAGE_BUCKET = os.environ['GCS_IMAGE_BUCKET']
datastore_client = datastore.Client()

@app.route('/')
def index():
    # Fetch the most recent 10 access times from Datastore.
    images = fetch_images(10)

    return render_template(
        'index.html', images=images)

#     return """
# <form method="POST" action="/upload" enctype="multipart/form-data">
#     <input type="file" name="file">
#     <input type="submit">
# </form>
# """

@app.route('/upload', methods=['POST'])
def upload():
    """Process the uploaded file and upload it to Google Cloud Storage."""
    uploaded_file = request.files.get('file')

    if not uploaded_file:
        return 'No file uploaded.', 400

    # Create a Cloud Storage client.
    gcs = storage.Client()

    # Get the bucket that the file will be uploaded to.
    bucket = gcs.get_bucket(GCS_IMAGE_BUCKET)

    # Create a new blob and upload the file's content.
    blob = bucket.blob(uploaded_file.filename)

    blob.upload_from_string(
        uploaded_file.read(),
        content_type=uploaded_file.content_type
    )

    photographer = request.form.get("photographer")
    location = request.form.get("location")
    date = request.form.get("date")

    store_image_data(blob.public_url, photographer, location, date)
    # The public URL can be used to directly access the uploaded file via HTTP.
    #return blob.public_url
    return render_template(
        'index.html', images=fetch_images(10))


def store_image_data(url, photographer,location, date):
    label = detect_labels_uri(url)
    entity = datastore.Entity(key=datastore_client.key('image'))
    entity.update({
        'url': url,
        'photographer': photographer,
        'location': location,
        'date': date,
        'label': label
    })
    datastore_client.put(entity)


def fetch_images(limit):
    query = datastore_client.query(kind='image')
    query.order = ['-url']

    images = query.fetch(limit=limit)
    return images


def detect_labels_uri(uri):
    """Detects labels in the file located in Google Cloud Storage or on the
    Web."""
    client = vision.ImageAnnotatorClient()
    image = vision.Image()
    image.source.image_uri = uri

    response = client.label_detection(image=image)
    labels = response.label_annotations
    print('Labels:')
    desc =""
    for label in labels:
        desc += label.description + ', '
        print(label.description)

    if response.error.message:
        raise Exception(
            '{}\nFor more info on error messages, check: '
            'https://cloud.google.com/apis/design/errors'.format(
                response.error.message))
    return desc


@app.route('/<id>')
def view(id):
    query = datastore_client.query(kind='image')
    id_key = datastore_client.key('image', int(id))
    query.key_filter(id_key, '=')
    results = query.fetch()
    return render_template("view.html", images=results)

@app.route('/edit', methods=['POST'])
def edit():
    photographer = request.form.get("photographer")
    location = request.form.get("location")
    date = request.form.get("date")
    id = request.form.get("id")
    #url = request.form.get("url")
    label = request.form.get("label")

    query = datastore_client.query(kind='image')
    id_key = datastore_client.key('image', int(id))
    query.key_filter(id_key, '=')
    entities = query.fetch()
    for entity in entities:
        """Process the uploaded file and upload it to Google Cloud Storage."""
        uploaded_file = request.files.get('file')

        if not uploaded_file:
            print('image not changed')
            entity["label"] = label
        else:
            # Create a Cloud Storage client.
            gcs = storage.Client()
            # Get the bucket that the file will be uploaded to.
            bucket = gcs.get_bucket(GCS_IMAGE_BUCKET)

            # Create a new blob and upload the file's content.
            blob = bucket.blob(uploaded_file.filename)

            blob.upload_from_string(
                uploaded_file.read(),
                content_type=uploaded_file.content_type
            )
            entity["url"] = blob.public_url
            entity["label"] = detect_labels_uri(blob.public_url)

        entity["location"] = location
        entity["date"] = date
        entity["photographer"] = photographer
        datastore_client.put(entity);

    return render_template(
        'index.html', images=fetch_images(10))

@app.errorhandler(500)
def server_error(e):
    logging.exception('An error occurred during a request.')
    return """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(e), 500


if __name__ == '__main__':
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host='127.0.0.1', port=8080, debug=True)
