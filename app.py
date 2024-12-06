import os
import time
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from email_utils import send_email_with_attachment
from flasgger import Swagger

# Initialisation de l'application Flask
app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = './uploads'
DATABASE_FILE = 'sqlite:///database.db'
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_FILE
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Initialisation de Swagger (documentation API)
swagger = Swagger(app)

# Initialisation de la base de données
db = SQLAlchemy(app)

# Création du dossier pour stocker les images
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Modèle pour les événements détectés
class DetectionEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    image_path = db.Column(db.String(120), nullable=False)

# Création de la base de données au démarrage
with app.app_context():
    db.create_all()

# Fonction pour nettoyer les fichiers anciens (plus de 7 jours)
def cleanup_old_files():
    now = time.time()
    for filename in os.listdir(UPLOAD_FOLDER):
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > 7 * 86400:  # 7 jours
            os.remove(file_path)
            print(f"Fichier supprimé : {file_path}")

# Endpoint pour télécharger une image
@app.route('/upload', methods=['POST'])
def upload_image():
    """
    Endpoint pour télécharger une image.
    ---
    parameters:
      - name: image
        in: formData
        type: file
        required: true
        description: L'image capturée à téléverser
    responses:
        200:
            description: Succès
        400:
            description: Erreur dans la requête
    """
    if 'image' not in request.files:
        return jsonify({"error": "Aucune image reçue"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "Le nom du fichier est vide"}), 400

    # Sauvegarder l'image
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    # Enregistrer l'événement dans la base de données
    event = DetectionEvent(image_path=file_path)
    db.session.add(event)
    db.session.commit()

    # Envoyer un e-mail avec la pièce jointe
    server_url = "http://localhost:5000"  # Remplacez par l'adresse de votre serveur
    image_url = f"{server_url}/images/{filename}"
    email_subject = "⚠️ Alerte Sécurité - Mouvement détecté"
    email_body = f"""
    Bonjour,

    Une alerte de sécurité a été générée à {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}.
    
    Détails :
    - Nom du fichier : {filename}
    - Chemin de l'image : {file_path}

    Vous pouvez consulter l'image directement en cliquant sur ce lien :
    {image_url}

    Veuillez vérifier immédiatement.

    Cordialement,
    Votre Système de Sécurité.
    """

    send_email_with_attachment(
        subject=email_subject,
        body=email_body,
        to_email="destinataire_email@gmail.com",
        attachment_path=file_path
    )

    return jsonify({"message": "Image reçue et notification envoyée !", "filename": filename}), 200

# Endpoint pour récupérer tous les logs
@app.route('/logs', methods=['GET'])
def get_logs():
    """
    Endpoint pour récupérer tous les logs d'événements.
    ---
    responses:
        200:
            description: Liste des événements
    """
    events = DetectionEvent.query.all()
    logs = [{"id": event.id, "timestamp": event.timestamp, "image_path": event.image_path} for event in events]
    return jsonify(logs)

# Endpoint pour accéder à une image spécifique
@app.route('/images/<filename>', methods=['GET'])
def get_image(filename):
    """
    Endpoint pour récupérer une image spécifique.
    ---
    parameters:
      - name: filename
        in: path
        type: string
        required: true
        description: Nom du fichier image
    responses:
        200:
            description: Image téléchargée
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Endpoint pour nettoyer les fichiers anciens
@app.route('/cleanup', methods=['GET'])
def cleanup():
    """
    Endpoint pour nettoyer les fichiers anciens (plus de 7 jours).
    ---
    responses:
        200:
            description: Nettoyage terminé
    """
    cleanup_old_files()
    return jsonify({"message": "Nettoyage terminé"})

# Endpoint pour supprimer un log spécifique
@app.route('/logs/<int:log_id>', methods=['DELETE'])
def delete_log(log_id):
    """
    Endpoint pour supprimer un log spécifique.
    ---
    parameters:
      - name: log_id
        in: path
        type: integer
        required: true
        description: ID de l'événement à supprimer
    responses:
        200:
            description: Log supprimé avec succès
        404:
            description: Log introuvable
    """
    event = DetectionEvent.query.get(log_id)
    if not event:
        return jsonify({"error": "Log introuvable"}), 404

    # Supprimer le fichier associé si existant
    if os.path.exists(event.image_path):
        os.remove(event.image_path)
        print(f"Fichier associé supprimé : {event.image_path}")

    # Supprimer l'événement de la base de données
    db.session.delete(event)
    db.session.commit()

    return jsonify({"message": f"Log avec ID {log_id} supprimé avec succès"}), 200

# Endpoint pour supprimer tous les logs
@app.route('/logs', methods=['DELETE'])
def delete_all_logs():
    """
    Endpoint pour supprimer tous les logs.
    ---
    responses:
        200:
            description: Tous les logs ont été supprimés
    """
    events = DetectionEvent.query.all()
    for event in events:
        # Supprimer les fichiers associés
        if os.path.exists(event.image_path):
            os.remove(event.image_path)
            print(f"Fichier associé supprimé : {event.image_path}")

        # Supprimer l'événement de la base de données
        db.session.delete(event)

    db.session.commit()
    return jsonify({"message": "Tous les logs ont été supprimés avec succès"}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
