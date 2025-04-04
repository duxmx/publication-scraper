class Base:
    def get_publications_by_author(self, author_name: str, rows: int = 10, first_name: str = "", middle_initial: str = "", last_name: str = ""):
        """
        Get publications by author name
        
        Args:
            author_name (str): The full author name (e.g., "John A Smith")
            rows (int, optional): Maximum number of publications to return. Defaults to 10.
            first_name (str, optional): The author's first name. Defaults to "".
            middle_initial (str, optional): The author's middle initial(s). Defaults to "".
            last_name (str, optional): The author's last name. Defaults to "".
            
        Returns:
            list: A list of publication dictionaries
        """
        pass

    def get_name(self):
        class_name = type(self).__name__
        return class_name
