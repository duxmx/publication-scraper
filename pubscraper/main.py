import json
import logging
import time
import os
import tablib

from openpyxl import load_workbook
from dateutil.parser import parse

import click
from click_loglevel import LogLevel

from pubscraper.version import __version__
import pubscraper.config as config

from pubscraper.APIClasses.PubMed import PubMed
from pubscraper.APIClasses.CrossRef import CrossRef
from pubscraper.APIClasses.WebOfScience import WebOfScience


LOG_FORMAT = config.LOGGER_FORMAT_STRING
LOG_LEVEL = config.LOGGER_LEVEL
logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
logger = logging.getLogger(__name__)

APIS = {
    "PubMed": PubMed(),
    "CrossRef": CrossRef(),
    "WebOfScience": WebOfScience(),
}


def parse_first_name_and_middle_initial(first_name):
    """
    Parse a first name string to extract the first name and middle initial
    
    This function handles cases where the middle initial is included with the first name.
    For example, "John A" would be parsed as first_name="John", middle_initial="A"
    
    Special handling for cases where the first name is just an initial:
    - "M" -> first_name="M", middle_initial=""
    - "M Brooke" -> first_name="M", middle_initial="B" (preserving the full middle name in the author_name)
    
    Args:
        first_name (str): The first name string, potentially including middle initial(s)
        
    Returns:
        tuple: (first_name, middle_initial, full_middle_name)
    """
    if not first_name:
        return "", "", ""
        
    # Split the first name string into parts
    parts = first_name.strip().split()
    
    # If there's only one part, it's just the first name
    if len(parts) <= 1:
        return first_name, "", ""
        
    # The first part is the first name
    parsed_first_name = parts[0]
    
    # The rest are potential middle names
    middle_parts = parts[1:]
    middle_initial = ""
    full_middle_name = " ".join(middle_parts)
    
    # Extract initials from middle parts
    for part in middle_parts:
        # If it's a single character or a character followed by a period, it's an initial
        if len(part) == 1 or (len(part) == 2 and part[1] == '.'):
            middle_initial += part[0]
        # If it's a longer word, we'll just take the first character as the initial
        else:
            middle_initial += part[0]
    
    return parsed_first_name, middle_initial, full_middle_name


def _is_same_author(name1, name2):
    """
    Check if two author names likely refer to the same person
    
    Args:
        name1 (str): First author name
        name2 (str): Second author name
        
    Returns:
        bool: True if names likely refer to the same person
    """
    # Normalize names (lowercase, remove extra spaces)
    name1 = " ".join(name1.lower().split())
    name2 = " ".join(name2.lower().split())
    
    # If names are exactly the same, return True
    if name1 == name2:
        return True
    
    # Split names into parts
    parts1 = name1.split()
    parts2 = name2.split()
    
    # Check if last names match
    if parts1[-1] != parts2[-1]:
        return False
    
    # Check if first initials match
    if parts1[0][0] != parts2[0][0]:
        return False
    
    # If we have middle initials, check if they match
    if len(parts1) > 2 and len(parts2) > 2:
        # Get middle initials
        mid1 = parts1[1][0] if len(parts1[1]) >= 1 else ""
        mid2 = parts2[1][0] if len(parts2[1]) >= 1 else ""
        
        if mid1 and mid2 and mid1 != mid2:
            return False
    
    return True


def filter_publications_by_affiliation(publications, keyword="University of Texas", target_author=None):
    """
    Filter publications to only include those where the target author has the specified affiliation
    
    Args:
        publications (list): List of publication dictionaries
        keyword (str, optional): Keyword to search for in author affiliations. Defaults to "University of Texas".
        target_author (str, optional): If provided, only check affiliations for this specific author.
                                      If None, check all authors.
        
    Returns:
        list: Filtered list of publications
    """
    if not publications:
        return []
        
    filtered_pubs = []
    
    for pub in publications:
        # Check if the publication has author affiliation data
        if "authors_with_affiliations" not in pub:
            # Skip publications without affiliation data
            continue
            
        # Check if the target author has the specified affiliation
        target_author_has_matching_affiliation = False
        
        for author in pub.get("authors_with_affiliations", []):
            # If target_author is specified, only check that specific author
            if target_author and not _is_same_author(author["name"], target_author):
                continue
                
            for affiliation in author.get("affiliations", []):
                if keyword.lower() in affiliation.lower():
                    target_author_has_matching_affiliation = True
                    break
                    
            if target_author_has_matching_affiliation:
                break
                
        # Only include publication if the target author has the matching affiliation
        if target_author_has_matching_affiliation:
            filtered_pubs.append(pub)
            
    return filtered_pubs


def deduplicate_publications(publications):
    """
    Deduplicate publications based on DOI or title+authors
    
    Args:
        publications (list): List of publication dictionaries
        
    Returns:
        list: Deduplicated list of publications
    """
    deduplicated_pubs = []
    doi_map = {}  # Map of DOI to index in deduplicated_pubs
    title_author_map = {}  # Map of title+authors to index in deduplicated_pubs
    duplicates_found = 0
    
    for pub in publications:
        doi = pub.get("doi", "").strip()
        title = pub.get("title", "").strip().lower()
        authors_str = pub.get("authors", "").strip().lower()
        source = pub.get("from", "Unknown")
        
        # Check if we already have this publication by DOI
        if doi and doi in doi_map:
            # Update the existing publication's source
            idx = doi_map[doi]
            existing_pub = deduplicated_pubs[idx]
            existing_sources = existing_pub.get("sources", [existing_pub.get("from", "Unknown")])
            if source not in existing_sources:
                existing_sources.append(source)
            existing_pub["sources"] = existing_sources
            existing_pub["from"] = ", ".join(existing_sources)
            logger.info(f"Found duplicate by DOI: {doi} from {source}, already found in {existing_sources[:-1]}")
            duplicates_found += 1
            continue
            
        # Check if we already have this publication by title and authors
        if title and authors_str and (title, authors_str) in title_author_map:
            # Update the existing publication's source
            idx = title_author_map[(title, authors_str)]
            existing_pub = deduplicated_pubs[idx]
            existing_sources = existing_pub.get("sources", [existing_pub.get("from", "Unknown")])
            if source not in existing_sources:
                existing_sources.append(source)
            existing_pub["sources"] = existing_sources
            existing_pub["from"] = ", ".join(existing_sources)
            logger.info(f"Found duplicate by title/authors: '{title}' from {source}, already found in {existing_sources[:-1]}")
            duplicates_found += 1
            continue
        
        # This is a new publication
        pub["sources"] = [source]
        deduplicated_pubs.append(pub)
        
        # Add to our maps for future reference
        if doi:
            doi_map[doi] = len(deduplicated_pubs) - 1
        if title and authors_str:
            title_author_map[(title, authors_str)] = len(deduplicated_pubs) - 1
    # TODO: This text is a little confusing, rephrase for clarity
    logger.info(f"Deduplicated {len(publications)} publications to {len(deduplicated_pubs)} (found {duplicates_found} duplicates)")
    return deduplicated_pubs


def set_logging_level(ctx, param, value):
    """
    Callback function for click that sets the logging level
    """
    logger.setLevel(value)
    return value


def set_log_file(ctx, param, value):
    """
    Callback function for click that sets a log file
    """
    if value:
        fileHandler = logging.FileHandler(value, mode="w")
        logFormatter = logging.Formatter(LOG_FORMAT)
        fileHandler.setFormatter(logFormatter)
        logger.addHandler(fileHandler)
    return value


def list_configured_apis(ctx, param, value):
    """
    Callback function for click that lists available APIs
    """
    if value:
        click.secho("Available endpoints:", underline=True)
        for endpoint in APIS.keys():
            click.secho(f"  {endpoint}", fg="blue")
        ctx.exit()


@click.command()
@click.version_option(__version__)
@click.option(
    "--log-level",
    type=LogLevel(),
    default=logging.INFO,
    is_eager=True,
    callback=set_logging_level,
    help="Set the log level",
    show_default=True,
)
@click.option(
    "--log-file",
    type=click.Path(writable=True),
    is_eager=True,
    callback=set_log_file,
    help="Set the log file",
)
@click.option(
    "-i",
    "--input_file",
    type=click.Path(exists=True),
    default="example_input.xlsx",
    help="Specify input file",
)
@click.option("-o", "--output_file", default="output", help="Specify output file")
@click.option(
    "-n",
    "--number",
    type=int,
    default=10,
    help="Specify max number of publications to receive for each author",
)
@click.option(
    "--apis",
    "-a",
    type=click.Choice(
        [api for api in APIS.keys()],
        case_sensitive=False,
    ),
    multiple=True,
    default=[api for api in APIS.keys()],
    show_default=True,
    help="Specify APIs to query",
)
@click.option(
    "--list",
    "list_apis",
    is_flag=True,
    default=False,
    is_eager=True,
    callback=list_configured_apis,
    help="Display APIs configured for search queries",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(
        ["json", "csv", "xlsx"],
        case_sensitive=False,
    ),
    default="json",
    show_default=True,
    help="Select the output format from: csv, xlsx, or json.",
)
@click.option(
    "--cutoff_date",
    "-cd",
    type=str,
    default=None,
    show_default=True,
    help="Specify the latest date to pull publications. Example input: 2024 or 2024-05 or 2024-05-10.",
)
@click.option(
    "--institution-column",
    type=str,
    default=None,
    help="Specify the name of the institution column in the Excel file if it's not one of the standard names (institution, root_institution_name, institution_name).",
)
@click.option(
    "--first-name-column",
    type=str,
    default=None,
    help="Specify the name of the first name column in the Excel file if it's not one of the standard names (first_name, firstname, first).",
)
@click.option(
    "--last-name-column",
    type=str,
    default=None,
    help="Specify the name of the last name column in the Excel file if it's not one of the standard names (last_name, lastname, last, surname).",
)
@click.option(
    "--middle-name-column",
    type=str,
    default=None,
    help="Specify the name of the middle name column in the Excel file if it's not one of the standard names (middle_name, middlename, middle, middle_initial).",
)
@click.option(
    "--affiliation",
    "-aff",
    type=str,
    default="University of Texas",
    show_default=True,
    help="Fallback keyword for filtering publications by affiliation when an author's institution is not available in the Excel file.",
)
@click.option(
    "--filter-by-affiliation",
    is_flag=True,
    default=True,
    show_default=True,
    help="Enable filtering publications by affiliation. Set to false with --no-filter-by-affiliation to disable.",
)

def main(
    log_level,
    log_file,
    input_file,
    number,
    output_file,
    apis,
    list_apis,
    format,
    cutoff_date,
    institution_column,
    first_name_column,
    last_name_column,
    middle_name_column,
    affiliation,
    filter_by_affiliation,
):
    logger.debug(f"Logging is set to level {logging.getLevelName(log_level)}")
    if log_file:
        logger.debug(f"Writing logs to {log_file}")

    logger.info(f"Querying the following APIs:\n{', '.join(apis)}")
    try:
        authors_workbook = load_workbook(filename=input_file, read_only=True)
        worksheet = authors_workbook[config.WS_NAME]
        rows = worksheet.rows

        name_dict = {}
        if worksheet.max_row > 1:
            # Get the header row to find column indices by name
            header_row = next(rows)
            headers = [cell.value for cell in header_row]
            
            # Find indices for required columns
            column_indices = {}
            required_columns = ["institution", "first_name", "middle_name", "last_name"]
            
            # Map column names to their indices
            for i, header in enumerate(headers):
                if header:
                    header_lower = header.lower()
                    # Check for variations of column names
                    # Check for custom column names first, then fall back to standard names
                    if institution_column and header_lower == institution_column.lower():
                        column_indices["institution"] = i
                        logger.debug(f"Using custom institution column: {institution_column}")
                    elif first_name_column and header_lower == first_name_column.lower():
                        column_indices["first_name"] = i
                        logger.debug(f"Using custom first name column: {first_name_column}")
                    elif last_name_column and header_lower == last_name_column.lower():
                        column_indices["last_name"] = i
                        logger.debug(f"Using custom last name column: {last_name_column}")
                    elif middle_name_column and header_lower == middle_name_column.lower():
                        column_indices["middle_name"] = i
                        logger.debug(f"Using custom middle name column: {middle_name_column}")
                    # Fall back to standard column names
                    elif header_lower in ["institution", "root_institution_name", "institution_name"]:
                        column_indices["institution"] = i
                    elif header_lower in ["first_name", "firstname", "first"]:
                        column_indices["first_name"] = i
                    elif header_lower in ["middle_name", "middlename", "middle", "middle_initial"]:
                        column_indices["middle_name"] = i
                    elif header_lower in ["last_name", "lastname", "last", "surname"]:
                        column_indices["last_name"] = i
            
            # Log found columns
            logger.debug(f"Found columns: {column_indices}")
            
            # Check if required columns were found
            missing_columns = [col for col in ["first_name", "last_name"] if col not in column_indices]
            if missing_columns:
                logger.error(f"Required columns not found in Excel file: {missing_columns}")
                logger.error(f"Available columns: {headers}")
                exit(1)
            
            # Process each row
            for row in rows:
                # Get values using column indices
                institution = ""
                if "institution" in column_indices:
                    institution = row[column_indices["institution"]].value if row[column_indices["institution"]].value else ""
                first_name = row[column_indices["first_name"]].value if row[column_indices["first_name"]].value else ""
                
                # Middle name is optional
                middle_name = ""
                if "middle_name" in column_indices:
                    middle_name = row[column_indices["middle_name"]].value if row[column_indices["middle_name"]].value else ""
                
                last_name = row[column_indices["last_name"]].value if row[column_indices["last_name"]].value else ""
                
                # Parse first name to extract any middle initial that might be included
                parsed_first_name, first_name_middle_initial, full_middle_name = parse_first_name_and_middle_initial(first_name)
                
                # If we found a middle initial in the first name, use it if no middle name was provided
                if first_name_middle_initial and not middle_name:
                    # If we have a full middle name, use that instead of just the initial
                    if full_middle_name:
                        middle_name = full_middle_name
                        logger.debug(f"Extracted full middle name '{middle_name}' from first name '{first_name}'")
                    else:
                        middle_name = first_name_middle_initial
                        logger.debug(f"Extracted middle initial '{middle_name}' from first name '{first_name}'")
                    
                    # Update first name to the parsed version (without middle initial)
                    first_name = parsed_first_name
                
                # Construct author name with middle name if present
                if middle_name:
                    author_name = f"{first_name} {middle_name} {last_name}"
                else:
                    author_name = f"{first_name} {last_name}"
                
                name_dict[author_name] = {"name": author_name, "institution": institution}
                logging.debug(f"Processed author: {author_name}")

        logging.debug(f"number of names in name_dict: {len(name_dict.keys())}")
    except FileNotFoundError:
        logger.error(f"Couldn't read input file {input_file}, exiting")
        exit(1)

    logger.debug(f"Querying the following APIs: {apis}")
    logger.debug(f"Requesting {number} publications for each author")

    authors_and_pubs = []

    for author in name_dict.keys():
        results = {author: []}
        # FIXME: we should filter by date before the API queries (if the API supports date filtering)
        authors_pubs = []
        
        # Get author info from the dictionary
        author_info = name_dict[author]
        author_parts = author.split()
        
        # Extract name components
        if len(author_parts) >= 2:
            # Get the first and last parts of the name
            raw_first_name = author_parts[0]
            last_name = author_parts[-1]
            
            # Parse the first name to extract any middle initial that might be included
            first_name, first_name_middle_initial, full_middle_name = parse_first_name_and_middle_initial(raw_first_name)
            
            # Extract middle initial from middle parts of the name
            middle_initial = ""
            if len(author_parts) > 2:
                # Join all middle parts
                middle_parts = author_parts[1:-1]
                # Extract initials from middle parts
                for part in middle_parts:
                    if len(part) == 1 or (len(part) == 2 and part[1] == '.'):
                        middle_initial += part[0]
            
            # If we found a middle initial in the first name, add it to any existing middle initial
            if first_name_middle_initial:
                # If we have a full middle name from the first name, use it for better matching
                if full_middle_name:
                    # Add the full middle name to the author name for better matching in the API
                    author_parts.insert(1, full_middle_name)
                    logger.debug(f"Added full middle name '{full_middle_name}' from first name to author name")
                
                middle_initial = first_name_middle_initial + middle_initial
                logger.debug(f"Added middle initial '{first_name_middle_initial}' from first name to existing middle initial")
        else:
            # Default values if name parsing fails
            first_name = author
            middle_initial = ""
            last_name = ""
        
        # Get institution from author info
        institution = author_info.get("institution", "")
        
        logger.debug(f"Parsed author: '{author}' into first_name='{first_name}', middle_initial='{middle_initial}', last_name='{last_name}', institution='{institution}'")
        
        for api_name in apis:
            api = APIS[api_name]
            # Pass the parsed name components and institution to the API
            pubs_found = api.get_publications_by_author(
                author, 
                number,
                first_name=first_name,
                middle_initial=middle_initial,
                last_name=last_name,
                institution=institution
            )
            if pubs_found:
                for pub in pubs_found:
                    publication_date_str = pub.get("publication_date", "")

                    # If a cutoff date is provided, check if the publication date is after it
                    if cutoff_date:
                        publication_date = (
                            parse(publication_date_str).strftime("%Y-%m-%d")
                            if publication_date_str
                            else ""
                        )
                        if publication_date and publication_date > cutoff_date:
                            authors_pubs.append(pub)
                    else:
                        authors_pubs.append(pub)
        
        # Deduplicate publications
        deduplicated_pubs = deduplicate_publications(authors_pubs)
        logger.info(f"Deduplicated {len(authors_pubs)} publications to {len(deduplicated_pubs)} for author {author}")
        
        # Apply affiliation filtering if enabled
        if filter_by_affiliation:
            # Get the author's institution from the Excel file
            author_institution = author_info.get("institution", "")
            
            # Use the author's institution for filtering if available, otherwise use the global affiliation parameter
            filter_keyword = author_institution if author_institution else affiliation
            
            # For PubMed, we've already filtered by institution in the API call
            # For other APIs, we need to apply post-processing filtering
            if "PubMed" in apis and len(apis) == 1:
                # If only PubMed is being used, no need for post-processing filtering
                filtered_pubs = deduplicated_pubs
                logger.info(f"Using {len(filtered_pubs)} publications for author {author} (pre-filtered by PubMed API)")
            else:
                # Apply post-processing filtering for other APIs or when multiple APIs are used
                filtered_pubs = filter_publications_by_affiliation(
                    deduplicated_pubs, 
                    keyword=filter_keyword,
                    target_author=author  # Pass the author name to check affiliations for this specific author
                )
                logger.info(f"Filtered {len(deduplicated_pubs)} publications to {len(filtered_pubs)} with '{filter_keyword}' affiliation for author {author}")
        else:
            # Skip affiliation filtering
            filtered_pubs = deduplicated_pubs
            logger.info(f"Skipping affiliation filtering (disabled by user). Using all {len(filtered_pubs)} publications for author {author}")
        
        results.update({author: filtered_pubs})
        authors_and_pubs.append(results)
        time.sleep(config.TIME_SLEEP)

    """
    Using TabLib to format data in specified format
    """
    logger.debug(f"Results: {(json.dumps(authors_and_pubs, indent=2))}")
    logger.info(f"Exporting the dataset in the specified format: {format} ")

    try:
        os.remove(output_file)
        logger.debug(f"successfully removed {output_file}")
    except Exception:
        logger.warning(f"could not remove {output_file}")

    dataset = tablib.Dataset()

    dataset.headers = [
        "From",
        "Author",
        "DOI",
        "Journal",
        "Content Type",
        "Publication Date",
        "Title",
        "Authors",
    ]

    # Loop through each author and their publications in authors_and_pubs
    for author_result in authors_and_pubs:
        for (
            author,
            publications,
        ) in author_result.items():  # Use .items() to unpack dictionary
            for pub in publications:
                if isinstance(pub, dict):  # Only process dictionary entries
                    # Safely fetch values using .get to avoid KeyError, defaulting to 'N/A' if the key is missing
                    dataset.append(
                        [
                            pub.get("from", "N/A"),
                            author,
                            pub.get("doi", "N/A"),
                            pub.get("journal", "N/A"),
                            pub.get("content_type", "N/A"),
                            pub.get("publication_date", "N/A"),
                            pub.get("title", "N/A"),
                            pub.get("authors", "N/A"),
                        ]
                    )

    if format == "xlsx":
        with open(f"output.{format}", "wb") as f:
            f.write(dataset.export("xlsx"))
    else:
        with open(f"output.{format}", "w") as f:
            if format == "csv":
                f.write(dataset.export("csv"))
            elif format == "json":
                json.dump(authors_and_pubs, f, indent=4)

    logger.info(f"Data successfully exported to {output_file}.{format}")

    return 0


if __name__ == "__main__":
    main()
