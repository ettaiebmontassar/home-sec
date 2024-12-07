import os
import time
import cv2
import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import smtplib

# Configuration pour les emails
EMAIL_SENDER = "taiebmontassar2003@gmail.com"
EMAIL_PASSWORD = "dnan xjkd ilqx fafj"
EMAIL_RECIPIENT = "ettaiebmontassar@gmail.com"

# Dossiers pour les données
KNOWN_FACES_DIR = "./known_faces"
ANNOTATED_IMAGES_DIR = "./annotated_images"
UPLOAD_FOLDER = './uploads'
DATABASE_FILE = 'sqlite:///database.db'

# Initialisation de l'application Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_FILE
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ANNOTATED_IMAGES_FOLDER'] = ANNOTATED_IMAGES_DIR

# Initialisation de la base de données
db = SQLAlchemy(app)

# Création des dossiers nécessaires
os.makedirs(KNOWN_FACES_DIR, exist_ok=True)
os.makedirs(ANNOTATED_IMAGES_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Modèle LBPH pour la reconnaissance faciale
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
face_recognizer = cv2.face.LBPHFaceRecognizer_create()

# Modèle pour les événements détectés
class DetectionEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(120), nullable=False)
    annotated_image_path = db.Column(db.String(120), nullable=True)

# Création de la base de données au démarrage
with app.app_context():
    db.create_all()

def send_alert_email(image_path):
    """
    Envoie une alerte par email avec l'image annotée en pièce jointe.
    """
    try:
        subject = "⚠️ Alerte de sécurité : Visage inconnu détecté"
        body = "Un visage inconnu a été détecté par le système de sécurité. Veuillez vérifier l'image en pièce jointe."

        # Configurer le contenu de l'email
        message = MIMEMultipart()
        message["From"] = EMAIL_SENDER
        message["To"] = EMAIL_RECIPIENT
        message["Subject"] = subject
        message.attach(MIMEText(body, "plain"))

        # Ajouter l'image annotée en pièce jointe
        with open(image_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(image_path)}"
        )
        message.attach(part)

        # Envoyer l'email
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(message)

        print("Alerte email envoyée avec l'image annotée.")
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email : {e}")

def train_model():
    """
    Entraîne le modèle LBPH avec les visages connus.
    """
    print("Entraînement du modèle LBPH...")
    faces = []
    labels = []
    label_id = 0
    label_map = {}

    IMAGE_SIZE = (200, 200)

    for label_name in os.listdir(KNOWN_FACES_DIR):
        label_dir = os.path.join(KNOWN_FACES_DIR, label_name)
        if not os.path.isdir(label_dir):
            continue

        label_map[label_id] = label_name
        for image_name in os.listdir(label_dir):
            image_path = os.path.join(label_dir, image_name)
            image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if image is None:
                continue

            resized_image = cv2.resize(image, IMAGE_SIZE)
            faces.append(resized_image)
            labels.append(label_id)

        label_id += 1

    if len(faces) == 0:
        print("Erreur : Aucun visage connu chargé.")
        exit()

    faces = np.array(faces, dtype="uint8")
    labels = np.array(labels, dtype="int32")

    face_recognizer.train(faces, labels)
    print("Modèle entraîné avec succès !")
    return label_map

def detect_and_recognize_faces(image_path, label_map):
    """
    Détecte et reconnaît les visages dans une image.
    """
    image = cv2.imread(image_path)
    if image is None:
        print("L'image n'a pas pu être chargée.")
        return False, None

    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray_image,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30)
    )

    face_detected = False
    for (x, y, w, h) in faces:
        face = gray_image[y:y+h, x:x+w]
        face = cv2.resize(face, (200, 200))

        label, confidence = face_recognizer.predict(face)
        name = label_map.get(label, "Inconnu") if confidence < 50 else "Inconnu"

        color = (0, 255, 0) if name != "Inconnu" else (0, 0, 255)
        cv2.rectangle(image, (x, y), (x+w, y+h), color, 2)
        cv2.putText(image, f"{name} ({confidence:.2f})", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

        if name == "Inconnu":
            face_detected = True

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    annotated_image_path = os.path.join(ANNOTATED_IMAGES_DIR, f"annotated_{timestamp}.jpg")
    cv2.imwrite(annotated_image_path, image)

    if face_detected:
        send_alert_email(annotated_image_path)

    return face_detected, annotated_image_path

@app.route('/upload', methods=['POST'])
def upload_and_analyze_image():
    """
    Endpoint pour télécharger et analyser une image.
    """
    if not request.data or request.content_length == 0:
        return jsonify({"error": "Aucune donnée reçue."}), 400

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_captured.jpg"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    with open(file_path, 'wb') as f:
        f.write(request.data)

    unknown_detected, annotated_image_path = detect_and_recognize_faces(file_path, label_map)

    event = DetectionEvent(image_path=file_path, annotated_image_path=annotated_image_path)
    db.session.add(event)
    db.session.commit()

    return jsonify({"message": "Image reçue et analysée.", "filename": filename, "unknown_detected": unknown_detected}), 200

@app.route('/logs', methods=['GET'])
def get_logs():
    events = DetectionEvent.query.all()
    logs = [{"id": event.id, "timestamp": event.timestamp, "image_path": event.image_path, "annotated_image_path": event.annotated_image_path} for event in events]
    return jsonify(logs)

@app.route('/images/<filename>', methods=['GET'])
def get_image(filename):
    """
    Récupérer une image spécifique.
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/cleanup', methods=['GET'])
def cleanup_old_files():
    """
    Nettoyer les fichiers anciens (plus de 7 jours).
    """
    now = time.time()
    for folder in [UPLOAD_FOLDER, ANNOTATED_IMAGES_DIR]:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > 7 * 86400:
                os.remove(file_path)
                print(f"Fichier supprimé : {file_path}")
    return jsonify({"message": "Nettoyage terminé"}), 200

@app.route('/logs/<int:log_id>', methods=['DELETE'])
def delete_log(log_id):
    """
    Supprimer un log spécifique.
    """
    event = DetectionEvent.query.get(log_id)
    if not event:
        return jsonify({"error": "Log introuvable"}), 404

    if os.path.exists(event.image_path):
        os.remove(event.image_path)
    if os.path.exists(event.annotated_image_path):
        os.remove(event.annotated_image_path)

    db.session.delete(event)
    db.session.commit()

    return jsonify({"message": f"Log avec ID {log_id} supprimé avec succès"}), 200

if __name__ == '__main__':
    label_map = train_model()
    app.run(debug=True, host='0.0.0.0', port=5000)