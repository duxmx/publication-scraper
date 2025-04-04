import requests
import json
import time
import logging
import xml.etree.ElementTree as ET
from dateutil.parser import parse
from datetime import datetime

from pubscraper.APIClasses.Base import Base
import pubscraper.config as config

logger = logging.getLogger(__name__)


class PubMed(Base):
    def __init__(self):
        self.search_url = config.PUBMED_SEARCH_URL
        self.summary_url = config.PUBMED_SUMMARY_URL
        self.fetch_url = config.PUBMED_FETCH_URL
        self.last_request_time = 0
        self.requests_per_second = 2  # PubMed can handle 3 requests/sec, we'll use 2 to be safe
        
    def _make_request(self, url, params=None, timeout=10):
        """
        Make a rate-limited request to the PubMed API
        
        This method enforces a rate limit of 2 requests per second to avoid
        overwhelming the PubMed API and getting rate-limited.
        
        Args:
            url (str): The URL to request
            params (dict, optional): Query parameters. Defaults to None.
            timeout (int, optional): Request timeout in seconds. Defaults to 10.
            
        Returns:
            requests.Response: The response from the API
            
        Raises:
            requests.exceptions.RequestException: If the request fails
        """
        # Calculate time since last request
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        # Calculate minimum time between requests based on rate limit
        min_interval = 1.0 / self.requests_per_second
        
        # Sleep if we need to wait to respect rate limit
        if time_since_last_request < min_interval:
            sleep_time = min_interval - time_since_last_request
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        # Make the request
        response = requests.get(url, params=params, timeout=timeout)
        
        # Update last request time
        self.last_request_time = time.time()
        
        # Check for errors
        response.raise_for_status()
        
        return response

    def _get_UIDs_by_author(self, author_name, rows=10):
        """
        Retrieve a given author's UID publications
        :param author_name: name of author {firstName} {lastName}
        :param rows: number of results to return (default is 10)
        :return: A list of UIDs corresponding to papers written by the author
        """
        # prepare Entrez query

        if rows < 0:
            logging.error(f"Rows must be a postive number (received {rows})")
            raise ValueError("Rows must be a positive number")

        if author_name == "":
            logging.warning("received empty string for author name, returning None")
            return None

        # PubMed searches by {lastName} {firstInitial}{midInitial}
        # searching by {firstName} {lastName} will always yield no results!
        split_name = author_name.split()
        if len(split_name) == 1:
            entrez_author_name = split_name[0] + "[author]"
        else:
            entrez_author_name = split_name[-1] + "+"
            for name in split_name[:-1]:
                entrez_author_name += "{initial}".format(initial=name[0])
            entrez_author_name += "[Author Name]"

        params = {
            "db": "pubmed",  # Changed from "pmc" to search the entire PubMed database
            "term": entrez_author_name,
            "retmax": rows,
            "retmode": "JSON",
        }

        # Error handling when interacting with PubMed APIs.
        try:
            response = self._make_request(self.search_url, params=params, timeout=10)  # Send the request to the PubMed API
        except requests.exceptions.RequestException as e:
            logging.error(f"PubMed API Request error: {e}")
            return None

        data = response.json()
        logging.debug(json.dumps(data, indent=2))
        id_list = data["esearchresult"]["idlist"]

        if not id_list:
            logging.warning(
                f"Received no UIDs for author {author_name}, returning None"
            )
            logging.debug(f'passed "{entrez_author_name}" to PubMed API')
            return None

        logging.debug(f"received the following UIDs: {id_list}")
        return id_list

    def _extract_DOI(self, summary_object) -> str:
        """
        Given a JSON object of a publication, extract and return the DOI
        :params summary_object: JSON result from PubMed eSummary
        :return: DOI of the article as a string
        """
        articleids = summary_object.get("articleids", [])
        for id in articleids:
            if id["idtype"] == "doi":
                return id["value"]

        return ""
        
    def _simplify_institution_name(self, institution):
        """
        Simplify institution name for better matching in PubMed queries
        
        This method:
        1. Removes anything in parentheses
        2. Removes anything after commas
        3. Extracts just the main part of the institution name
        
        Args:
            institution (str): Original institution name (e.g., "University of Texas at Austin (utexas.edu)")
            
        Returns:
            str: Simplified institution name (e.g., "University of Texas")
        """
        if not institution:
            return ""
            
        # Remove anything in parentheses
        simplified = institution.split('(')[0].strip()
        
        # Extract the main part (e.g., "University of Texas" from "University of Texas at Austin")
        main_parts = []
        for part in simplified.split():
            main_parts.append(part)
            # If we have "University of X", that's usually enough for matching
            if len(main_parts) >= 3 and main_parts[-3] == "University" and main_parts[-2] == "of":
                break
                
        # If we didn't find "University of X" pattern, just use the first 3 words or up to the first comma
        if len(main_parts) < 3 or main_parts[-3] != "University" or main_parts[-2] != "of":
            # Use everything before the first comma, or the first 3 words
            comma_split = simplified.split(',')[0].strip()
            words = comma_split.split()
            main_parts = words[:min(3, len(words))]
            
        simplified = ' '.join(main_parts)
        
        logging.debug(f"Simplified institution name: '{institution}' -> '{simplified}'")
        return simplified

    def _get_publication_details_with_affiliations(self, UIDs):
        """
        Retrieve detailed publication information including author affiliations using EFetch
        
        Args:
            UIDs (list): List of PubMed UIDs
            
        Returns:
            list: List of publication dictionaries with affiliation data
        """
        if not UIDs:
            logging.warning("Received no UIDs, returning None")
            return None
            
        # Join UIDs list into one 'csv' string
        stringified_UIDs = ",".join(UIDs)
        
        # First get summary data using ESummary
        summary_params = {
            "db": "pubmed",  # Changed from "pmc" to search the entire PubMed database
            "id": stringified_UIDs,
            "retmode": "JSON",
        }
        
        try:
            summary_response = self._make_request(self.summary_url, params=summary_params, timeout=10)
            summary_data = summary_response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching summaries from PubMed: {e}")
            return None
            
        # Then get detailed data including affiliations using EFetch
        fetch_params = {
            "db": "pubmed",  # Changed from "pmc" to search the entire PubMed database
            "id": stringified_UIDs,
            "retmode": "xml",
        }
        
        try:
            fetch_response = self._make_request(self.fetch_url, params=fetch_params, timeout=15)
            fetch_data = fetch_response.text
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching detailed data from PubMed: {e}")
            # If EFetch fails, fall back to summary data without affiliations
            return self._process_summary_data(summary_data)
            
        # Process the XML data to extract affiliations
        try:
            return self._process_fetch_data(fetch_data, summary_data)
        except Exception as e:
            logging.error(f"Error processing EFetch data: {e}")
            # If processing fails, fall back to summary data without affiliations
            return self._process_summary_data(summary_data)
    
    def _process_fetch_data(self, xml_data, summary_data):
        """
        Process XML data from EFetch to extract publication details including affiliations
        
        Args:
            xml_data (str): XML response from EFetch
            summary_data (dict): JSON response from ESummary
            
        Returns:
            list: List of publication dictionaries with affiliation data
        """
        publications = []
        
        try:
            # Parse XML
            root = ET.fromstring(xml_data)
            
            # Process each article
            for article in root.findall('.//PubmedArticle'):
                pmid = article.find('.//PMID').text if article.find('.//PMID') is not None else ""
                
                # Get summary data for this article
                if pmid and pmid in summary_data["result"]:
                    summary_object = summary_data["result"][pmid]
                else:
                    # If we can't match with summary data, skip this article
                    continue
                
                # Extract basic publication info
                title = summary_object.get("title", "")
                journal = summary_object.get("fulljournalname", "")
                
                # Standardize the publication date
                raw_publication_date = summary_object.get("sortdate", "")
                try:
                    publication_date = parse(raw_publication_date).strftime("%Y-%m-%d")
                except Exception as e:
                    logging.warning(f"Error parsing publication date: {e}")
                    publication_date = None
                
                # Extract DOI
                doi = self._extract_DOI(summary_object)
                
                # Extract authors with affiliations
                authors_with_affiliations = []
                author_names = []
                
                # Find all authors in the XML
                author_elements = article.findall('.//Author')
                
                for author_elem in author_elements:
                    # Extract author name
                    last_name = author_elem.find('LastName').text if author_elem.find('LastName') is not None else ""
                    first_name = author_elem.find('ForeName').text if author_elem.find('ForeName') is not None else ""
                    author_name = f"{first_name} {last_name}".strip()
                    
                    if not author_name:
                        continue
                        
                    author_names.append(author_name)
                    
                    # Extract affiliations
                    affiliations = []
                    affiliation_elems = author_elem.findall('.//Affiliation')
                    
                    for aff_elem in affiliation_elems:
                        if aff_elem is not None and aff_elem.text:
                            affiliations.append(aff_elem.text)
                    
                    # Add author with affiliations
                    authors_with_affiliations.append({
                        "name": author_name,
                        "affiliations": affiliations
                    })
                
                # Create publication object
                pub = {
                    "from": "PubMed",
                    "journal": journal,
                    "publication_date": publication_date,
                    "title": title,
                    "authors": ",".join(author_names),
                    "authors_with_affiliations": authors_with_affiliations,
                    "doi": doi,
                }
                
                publications.append(pub)
                
        except ET.ParseError as e:
            logging.error(f"Error parsing XML data: {e}")
            # Fall back to summary data
            return self._process_summary_data(summary_data)
            
        return publications
    
    def _process_summary_data(self, summary_data):
        """
        Process JSON data from ESummary (fallback if EFetch fails)
        
        Args:
            summary_data (dict): JSON response from ESummary
            
        Returns:
            list: List of publication dictionaries without affiliation data
        """
        publications = []
        
        for uid in summary_data["result"]["uids"]:
            summary_object = summary_data["result"][uid]
            author_list = []
            
            for author_object in summary_object.get("authors", []):
                author_list.append(author_object.get("name", ""))
            
            # Standardize the publication date
            raw_publication_date = summary_object.get("sortdate", "")
            try:
                publication_date = parse(raw_publication_date).strftime("%Y-%m-%d")
            except Exception as e:
                logging.warning(f"Error parsing publication date: {e}")
                publication_date = None
                
            pub = {
                "from": "PubMed",
                "journal": summary_object.get("fulljournalname", ""),
                "publication_date": publication_date,
                "title": summary_object.get("title", ""),
                "authors": ",".join(author_list),
                "doi": self._extract_DOI(summary_object),
            }
            
            publications.append(pub)
            
        return publications
    
    def _get_summary_by_UIDs(self, UIDs):
        """
        Given a list of UIDs, retrieve summary information for each UID including author affiliations
        
        Args:
            UIDs (list): A list of UIDs
            
        Returns:
            list: A list of publication objects/dicts with author affiliations
        """
        return self._get_publication_details_with_affiliations(UIDs)

    def get_publications_by_author(self, author_name, rows=10, first_name="", middle_initial="", last_name="", institution=""):
        """
        Given the name of an author, search PubMed Central for
        works written by that author name, optionally filtering by institution
        
        Args:
            author_name (str): The full author name (e.g., "John A Smith")
            rows (int, optional): Maximum number of publications to return. Defaults to 10.
            first_name (str, optional): The author's first name. Defaults to "".
            middle_initial (str, optional): The author's middle initial(s). Defaults to "".
            last_name (str, optional): The author's last name. Defaults to "".
            institution (str, optional): Institution to filter by. Defaults to "".
            
        Returns:
            list: A list of publication dictionaries
        """
        # If we have the parsed name components, use them for a more accurate search
        if first_name and last_name:
            # PubMed searches by {lastName} {firstInitial}{midInitial}
            entrez_author_name = last_name + "+"
            if first_name:
                entrez_author_name += first_name[0]
            if middle_initial:
                entrez_author_name += middle_initial
            entrez_author_name += "[Author Name]"
            
            logging.debug(f"Using parsed name components for PubMed search: {entrez_author_name}")
            
            # If institution is provided, include it in the search query
            if institution:
                # Simplify the institution name for better matching
                simplified_institution = self._simplify_institution_name(institution)
                entrez_query = f"{entrez_author_name} AND {simplified_institution}[AFFL]"
                logging.debug(f"Searching for author with institution: {entrez_query}")
                UIDs = self._get_UIDs_by_query(entrez_query, rows)
                
                # If no results with institution filter, try author-only query as fallback
                if not UIDs:
                    logging.warning(f"No results found with institution filter, trying author-only query")
                    UIDs = self._get_UIDs_by_author_components(entrez_author_name, rows)
            else:
                UIDs = self._get_UIDs_by_author_components(entrez_author_name, rows)
        else:
            # Fall back to the original method if we don't have parsed components
            logging.debug(f"Using original author name for PubMed search: {author_name}")
            
            # If institution is provided, include it in the search query
            if institution:
                # Prepare Entrez query with author and institution
                split_name = author_name.split()
                if len(split_name) == 1:
                    entrez_author_name = split_name[0] + "[author]"
                else:
                    entrez_author_name = split_name[-1] + "+"
                    for name in split_name[:-1]:
                        entrez_author_name += "{initial}".format(initial=name[0])
                    entrez_author_name += "[Author Name]"
                
                # Simplify the institution name for better matching
                simplified_institution = self._simplify_institution_name(institution)
                entrez_query = f"{entrez_author_name} AND {simplified_institution}[AFFL]"
                logging.debug(f"Searching for author with institution: {entrez_query}")
                UIDs = self._get_UIDs_by_query(entrez_query, rows)
                
                # If no results with institution filter, try author-only query as fallback
                if not UIDs:
                    logging.warning(f"No results found with institution filter, trying author-only query")
                    UIDs = self._get_UIDs_by_author(author_name, rows)
            else:
                UIDs = self._get_UIDs_by_author(author_name, rows)
            
        summary_info = self._get_summary_by_UIDs(UIDs)
        return summary_info
        
    def _get_UIDs_by_query(self, entrez_query, rows=10):
        """
        Retrieve publication UIDs using a complete Entrez query string
        
        Args:
            entrez_query (str): Complete Entrez query string (e.g., "Smith J[Author] AND University of Texas[AFFL]")
            rows (int, optional): Number of results to return. Defaults to 10.
            
        Returns:
            list: A list of UIDs corresponding to papers matching the query
        """
        if rows < 0:
            logging.error(f"Rows must be a postive number (received {rows})")
            raise ValueError("Rows must be a positive number")

        if not entrez_query:
            logging.warning("received empty string for query, returning None")
            return None

        params = {
            "db": "pubmed",  # Changed from "pmc" to search the entire PubMed database
            "term": entrez_query,
            "retmax": rows,
            "retmode": "JSON",
        }

        # Error handling when interacting with PubMed APIs.
        try:
            response = self._make_request(self.search_url, params=params, timeout=10)
        except requests.exceptions.RequestException as e:
            logging.error(f"PubMed API Request error: {e}")
            return None

        data = response.json()
        logging.debug(json.dumps(data, indent=2))
        id_list = data["esearchresult"]["idlist"]

        if not id_list:
            logging.warning(
                f"Received no UIDs for query: {entrez_query}, returning None"
            )
            return None

        logging.debug(f"received the following UIDs: {id_list}")
        return id_list
        
    def _get_UIDs_by_author_components(self, entrez_author_name, rows=10):
        """
        Retrieve a given author's UID publications using pre-formatted Entrez query
        
        Args:
            entrez_author_name (str): Pre-formatted author name for Entrez query
            rows (int, optional): Number of results to return. Defaults to 10.
            
        Returns:
            list: A list of UIDs corresponding to papers written by the author
        """
        if rows < 0:
            logging.error(f"Rows must be a postive number (received {rows})")
            raise ValueError("Rows must be a positive number")

        if not entrez_author_name:
            logging.warning("received empty string for author name, returning None")
            return None

        params = {
            "db": "pubmed",  # Changed from "pmc" to search the entire PubMed database
            "term": entrez_author_name,
            "retmax": rows,
            "retmode": "JSON",
        }

        # Error handling when interacting with PubMed APIs.
        try:
            response = self._make_request(self.search_url, params=params, timeout=10)
        except requests.exceptions.RequestException as e:
            logging.error(f"PubMed API Request error: {e}")
            return None

        data = response.json()
        logging.debug(json.dumps(data, indent=2))
        id_list = data["esearchresult"]["idlist"]

        if not id_list:
            logging.warning(
                f"Received no UIDs for author query {entrez_author_name}, returning None"
            )
            return None

        logging.debug(f"received the following UIDs: {id_list}")
        return id_list


def search_multiple_authors(authors, rows=10):
    """
    Search PubMed Central for works written by multiple authors
    :params authors: list of author names
    :params rows: maximum number of publications to return per author (default is 10)
    :return: a dict {author_name: {summary_info}} for each author
    """
    pubmed = PubMed()
    all_results = {}

    for author in authors:
        logging.debug(f"Searching for publications by {author}...")
        if author == "":
            logging.warning("received empty string for author name, continuing...")
            continue
        try:
            publications = pubmed.get_publications_by_author(author, rows)
            all_results[author] = publications
        except Exception as e:
            logging.error(f"Error fetching data for {author}: {e}")
        # No need for manual sleep here as the _make_request method handles rate limiting

    return all_results


def main():
    author_names = input("Enter author names (comma-separated): ").split(",")
    author_names = [name.strip() for name in author_names]

    results = search_multiple_authors(author_names)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
