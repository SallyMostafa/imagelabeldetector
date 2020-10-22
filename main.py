import logging
import os
import google.cloud.storage as storage
from google.cloud import datastore
from google.cloud import vision
from flask import Flask, request, render_template
import nltk
nltk.download('wordnet')
from nltk.corpus import wordnet as wn

app = Flask(__name__)

# Configure this environment variable via app.yaml
GCS_IMAGE_BUCKET = os.environ['GCS_IMAGE_BUCKET']
datastore_client = datastore.Client()
limit = 1000
@app.route('/')
def index():
    # Fetch the most recent 10 access times from Datastore.
    animals, flowers, people, others = fetch_images(limit)
    return render_template(
        'index.html', animals=animals, flowers=flowers, people=people, others=others)



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
    animals, flowers, people, others = fetch_images(limit)
    return render_template(
        'index.html', animals=animals, flowers=flowers, people=people, others=others)


def store_image_data(url, photographer,location, date):
    label, category = detect_labels_uri(url)
    entity = datastore.Entity(key=datastore_client.key('image'))
    entity.update({
        'url': url,
        'photographer': photographer,
        'location': location,
        'date': date,
        'label': label,
        'category': category
    })
    datastore_client.put(entity)


def fetch_images(limit):
    query = datastore_client.query(kind='image')
    query.order = ['-url']
    images = list(query.fetch(limit=limit))

    animals = [image for image in images if "category" in image and image["category"] == "animal"]
    flowers = [image for image in images if "category" in image and image["category"] == "flower"]
    people = [image for image in images if "category" in image and image["category"] == "people"]
    others = [image for image in images if "category" in image and image["category"] == "other"]

    return animals, flowers, people, others


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
    label_desc =[]
    for label in labels:
        desc += label.description + ', '
        label_desc.append(label.description)
        print(label.description)

    category = detect_category(label_desc)

    if response.error.message:
        raise Exception(
            '{}\nFor more info on error messages, check: '
            'https://cloud.google.com/apis/design/errors'.format(
                response.error.message))
    return desc, category


@app.route('/<id>')
def view(id):
    query = datastore_client.query(kind='image')
    id_key = datastore_client.key('image', int(id))
    query.key_filter(id_key, '=')
    results = query.fetch()
    return render_template("view.html", images=results)

@app.route('/delete', methods=['POST'])
def delete():
    id = request.form.get("delete_id")
    id_key = datastore_client.key('image', int(id))
    datastore_client.delete(id_key)
    animals, flowers, people, others = fetch_images(limit)
    return render_template(
        'index.html', animals=animals, flowers=flowers, people=people, others=others)

@app.route('/edit', methods=['POST'])
def edit():
    photographer = request.form.get("photographer")
    location = request.form.get("location")
    date = request.form.get("date")
    id = request.form.get("id")
    label = request.form.get("label")
    category = request.form.get("category")

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
            entity["category"] = category
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
            entity["label"], entity["category"] = detect_labels_uri(blob.public_url)

        entity["location"] = location
        entity["date"] = date
        entity["photographer"] = photographer
        datastore_client.put(entity);

    animals, flowers, people, others = fetch_images(limit)
    return render_template(
        'index.html', animals=animals, flowers=flowers, people=people, others=others)


def detect_category(labels):
    index = 0
    while (' ' in labels[index]) == True:
        index += 1

    if (' ' in labels[index]) == False:
        label = wn.synsets(labels[index])[0]
        animal = wn.synsets('animal')[0]
        flower = wn.synsets('flower')[0]
        people = wn.synsets('people')[0]

        print("animal")
        print(wn.synsets('animal')[0])
        print("flower")
        print(wn.synsets('flower')[0])
        print("people")
        print(wn.synsets('people')[0])

        animal_sim = label.wup_similarity(animal)
        flower_sim = label.wup_similarity(flower)
        people_sim = label.wup_similarity(people)

        similarity_dic = {"animal": animal_sim, "flower": flower_sim, "people": people_sim}
        print("animal similarity: ", animal_sim)
        print("flower similarity: ", flower_sim )
        print("people similarity: ", people_sim)

        # the key whose value is the largest
        key = max(similarity_dic, key=lambda k: similarity_dic[k])
        print("The key with the largest value:", key)

        # getting the largest value
        best_match_score = similarity_dic[key]
        print("The largest value:", best_match_score)
        if best_match_score < 0.55:
            key ="other"
        return key
    else:
        return "other"


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
