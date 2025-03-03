import requests
import json
import logging
import os
import time
from dotenv import load_dotenv
from dateutil.parser import parse

from pubscraper.APIClasses.Base import Base
import pubscraper.config as config

logger = logging.getLogger(__name__)


class WebOfScience(Base):
    def __init__(self):
        """
        Initialize the Web of Science API client.
        """
        load_dotenv()

        self.api_url = config.WOS_URL
        self.api_key = os.getenv("WOS_API_KEY")

    def get_publications_by_author(self, author_name, rows=10):
        """
        Retrieve publications from Web of Science by author name.
        :param author_name: The name of the author to search for
        :param rows: The number of results to return (default is 10)
        :return: A list of dictionaries containing publication details
        """
        logging.debug(f"requesting {rows} publications from {author_name}")

        if rows < 0:
            logging.error(f"Rows must be a positive number (received {rows})")
            raise ValueError("Rows must be a positive number")

        if not author_name.strip():
            logging.warning("Received empty string for author name in search query, returning None")
            return None

        # Split the author name into first name, middle name(s), and last name
        split_name = author_name.split()
        if len(split_name) == 1:
            last_name = split_name[0]
            first_name = ""
            middle_names = []
        elif len(split_name) == 2:
            last_name = split_name[-1]
            first_name = split_name[0]
            middle_names = []
        else:
            last_name = split_name[-1]
            first_name = split_name[0]
            middle_names = split_name[1:-1]

        # Construct the query for Web of Science
        # Format: AU=(Last_Name First_Initial Middle_Initial*)
        initials = ""
        if first_name:
            initials = first_name[0]
        for middle_name in middle_names:
            if middle_name:
                initials += middle_name[0]
        
        query = f"AU=({last_name} {initials}*)"
        logging.debug(f"Web of Science query: {query}")
        
        headers = {
            "X-ApiKey": self.api_key,
            "Content-Type": "application/json"
        }
        
        params = {
            "databaseId": "WOS",
            "usrQuery": query,
            "count": rows,
            "firstRecord": 1
        }
        
        # Error handling when interacting with Web of Science API
        try:
            response = requests.get(
                f"{self.api_url}/searches",
                headers=headers,
                params=params,
                timeout=30
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Web of Science API Request error: {e}")
            return []
        
        # Parse the JSON response
        data = response.json()
        logging.debug(json.dumps(data, indent=2))
        
        # Check if we have results
        if "Data" not in data or "Records" not in data["Data"]:
            logging.warning(f"No publications found for author {author_name}")
            return []
        
        # Extract publication records
        publications = []
        
        for record in data["Data"]["Records"]:
            try:
                # Extract DOI
                doi = ""
                if "Other" in record and "Identifiers" in record["Other"]:
                    for identifier in record["Other"]["Identifiers"]:
                        if identifier["Type"] == "Doi":
                            doi = identifier["Value"]
                            break
                
                # Extract journal name
                journal = record.get("Source", {}).get("SourceTitle", "")
                
                # Extract publication date
                pub_date = record.get("Source", {}).get("PublicationDate", "")
                try:
                    publication_date = parse(pub_date).strftime("%Y-%m-%d")
                except Exception as e:
                    logging.warning(f"Error parsing publication date: {e}")
                    publication_date = pub_date
                
                # Extract title
                title = record.get("Title", {}).get("Title", "")
                
                # Extract authors
                authors = []
                if "Authors" in record:
                    for author in record["Authors"]:
                        author_name = f"{author.get('LastName', '')}, {author.get('FirstName', '')}"
                        authors.append(author_name)
                
                # Create publication object
                if all([title, authors, publication_date, journal]):
                    pub = {
                        "from": "WebOfScience",
                        "journal": journal,
                        "publication_date": publication_date,
                        "title": title,
                        "authors": ", ".join(authors),
                        "doi": doi,
                        "content_type": record.get("DocumentType", "")
                    }
                    publications.append(pub)
            except Exception as e:
                logging.error(f"Error processing record: {e}")
                continue
        
        return publications


def search_multiple_authors(authors, limit=10):
    """
    Search for publications by multiple authors.
    :param authors: List of author names to search for
    :param limit: The number of results to return per author (default is 10)
    :return: Dictionary with results for each author
    """
    wos = WebOfScience()
    all_results = {}

    for author in authors:
        logging.debug(f"Searching for publications by {author}...")
        if not author.strip():
            logging.warning("Received empty string for author name, continuing...")
            continue
        try:
            # Get publications for each author, passing the limit (rows) to get_publications_by_author
            publications = wos.get_publications_by_author(author, rows=limit)
            all_results[author] = publications if publications else []
        except Exception as e:
            logging.error(f"Error fetching data for {author}: {e}")
            all_results[author] = []
        time.sleep(0.4)  # avoids potential rate limit violations

    return all_results


# Example usage:
if __name__ == "__main__":
    # Input: list of author names (comma-separated input)
    author_names = input("Enter author names (comma-separated): ").split(",")

    # Strip any leading/trailing whitespace
    author_names = [name.strip() for name in author_names]

    # Get results for all authors
    results = search_multiple_authors(author_names)

    # Output the results in JSON format
    print(json.dumps(results, indent=4))
