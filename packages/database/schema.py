# schema of mongodb database
from pymongo import MongoClient


class Database:
    """MongoDB database wrapper for managing ticket collections.

    Provides CRUD operations for ticket data stored in MongoDB collections.
    """

    def __init__(self, collection):
        """Initialize database connection and select collection.

        Args:
            collection: Name of the MongoDB collection to use.
        """
        self.client = MongoClient("mongodb://10.130.163.217:27017")
        self.db = self.client["tickets"]
        self.collection = self.db[collection]

    def get_all_collections(self):
        """Get list of all collection names in the tickets database.

        Returns:
            List of collection names.
        """
        return self.client.get_database("tickets").list_collection_names()

    def iscollection_present(self):
        """Check if the current collection exists in the database.

        Returns:
            bool: True if collection exists, False otherwise.
        """
        return self.collection.name in self.client.get_database("tickets").list_collection_names()

    def insert(self, data):
        """Insert multiple documents into the collection.

        Args:
            data: List of documents to insert.

        Returns:
            bool: True if insertion was acknowledged.
        """
        return self.collection.insert_many(data).acknowledged

    def find(self, id):
        """Find a single document by ID.

        Args:
            id: The document ID to search for.

        Returns:
            Document matching the ID, or None if not found.
        """
        return self.collection.find_one({"_id": id})

    def find_all(self):
        """Retrieve all documents from the collection.

        Returns:
            Cursor to iterate over all documents.
        """
        return self.collection.find()

    def delete(self, id):
        """Delete a single document by ID.

        Args:
            id: The document ID to delete.

        Returns:
            bool: True if deletion was acknowledged.
        """
        return self.collection.delete_one({"_id": id}).acknowledged

    def delete_all(self):
        """Delete all documents from the collection.

        Returns:
            bool: True if deletion was acknowledged.
        """
        return self.collection.delete_many({}).acknowledged

    def update(self, id, data):
        """Update a document by ID with new data.

        Updates all fields except comments.

        Args:
            id: The document ID to update.
            data: Dictionary of fields to update.

        Returns:
            UpdateResult object from MongoDB.
        """
        return self.collection.update_one({"_id": id}, {"$set": data})

    def delete_collection(self):
        """Delete the entire collection from the database."""
        return self.db.drop_collection(self.collection.name)

    def update_effort(self, id, data):
        """Update the effort field of a document.

        Args:
            id: The document ID to update.
            data: New effort value.

        Returns:
            bool: True if update was acknowledged.
        """
        return self.collection.update_one({"_id": id}, {"$set": {"Effort": data}}).acknowledged

    def count(self):
        """Count total number of documents in the collection.

        Returns:
            int: Number of documents.
        """
        return self.collection.count_documents({})

    def update_comments(self, id, data):
        """Add a new comment to a document's comments array.

        Args:
            id: The document ID to update.
            data: Comment to append to the comments array.

        Returns:
            bool: True if update was acknowledged.
        """
        return self.collection.update_one({"_id": id}, {"$push": {"comments": data}}).acknowledged

    def close(self):
        """Close the MongoDB client connection."""
        self.client.close()

# arr = ['7.2.1', '7.1', '7.1.1', '8.0.0', '7.0']
# for i in arr:
#     db=Database(i)
#     print(db.delete_collection()) #db.delete_collection()
# db=Database('7.2')
# print(db.get_all_collections())
# print(db.update_effort(id="SWDEV-562745" , data='XL'))
