import json
import logging
from pubscraper.main import deduplicate_publications

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_deduplication():
    # Create test data with duplicate publications
    publications = [
        {
            "from": "PubMed",
            "journal": "Nature",
            "publication_date": "2023-01-01",
            "title": "Test Publication 1",
            "authors": "Author A, Author B",
            "doi": "10.1234/test1"
        },
        {
            "from": "CrossRef",
            "journal": "Nature",
            "publication_date": "2023-01-01",
            "title": "Test Publication 1",
            "authors": "Author A, Author B",
            "doi": "10.1234/test1"  # Same DOI as the first publication
        },
        {
            "from": "ArXiv",
            "journal": "Nature",
            "publication_date": "2023-01-01",
            "title": "Test Publication 2",
            "authors": "Author C, Author D",
            "doi": "10.1234/test2"
        },
        {
            "from": "PLOS",
            "journal": "PLOS ONE",
            "publication_date": "2023-02-01",
            "title": "Test Publication 3",
            "authors": "Author E, Author F",
            "doi": ""  # No DOI
        },
        {
            "from": "Springer",
            "journal": "PLOS ONE",
            "publication_date": "2023-02-01",
            "title": "test publication 3",  # Same title as the previous publication (case insensitive)
            "authors": "author e, author f",  # Same authors as the previous publication (case insensitive)
            "doi": ""  # No DOI
        }
    ]
    
    # Call the deduplication function
    deduplicated = deduplicate_publications(publications)
    
    # Print the results
    print(f"Original publications: {len(publications)}")
    print(f"Deduplicated publications: {len(deduplicated)}")
    print("\nDeduplicated publications:")
    print(json.dumps(deduplicated, indent=2))
    
    # Verify the results
    assert len(deduplicated) == 3, f"Expected 3 deduplicated publications, got {len(deduplicated)}"
    
    # Check that the sources are combined correctly
    for pub in deduplicated:
        if pub["doi"] == "10.1234/test1":
            assert "PubMed" in pub["sources"] and "CrossRef" in pub["sources"], "Sources not combined correctly for DOI 10.1234/test1"
            assert pub["from"] == "PubMed, CrossRef", f"From field not updated correctly: {pub['from']}"
        elif pub["title"].lower() == "test publication 3":
            assert "PLOS" in pub["sources"] and "Springer" in pub["sources"], "Sources not combined correctly for 'Test Publication 3'"
            assert pub["from"] == "PLOS, Springer", f"From field not updated correctly: {pub['from']}"
    
    print("\nAll tests passed!")

if __name__ == "__main__":
    test_deduplication()
