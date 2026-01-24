"""Repository for Property model"""
from typing import Dict, Any, List, Optional
from models.property import Property
from repositories.base_repository import BaseRepository


class PropertyRepository(BaseRepository[Property]):
    """Repository for managing properties"""

    def __init__(self):
        super().__init__('properties')

    def to_model(self, data: Dict[str, Any]) -> Property:
        """Convert Firestore document to Property model"""
        return Property.from_dict(data)

    def to_dict(self, model: Property) -> Dict[str, Any]:
        """Convert Property model to Firestore document"""
        return model.to_dict()

    def create_property(self, property_model: Property, property_id: str) -> Property:
        """
        Create a new property

        Args:
            property_model: Property model instance
            property_id: Unique property ID string

        Returns:
            Created Property model
        """
        return self.create(property_id, property_model)

    def get_property(self, property_id: str) -> Optional[Property]:
        """
        Get property by ID

        Args:
            property_id: Property ID string

        Returns:
            Property model or None
        """
        return self.get(property_id)

    def get_properties_by_user(self, user_id: str) -> List[tuple[str, Property]]:
        """
        Get all properties for a user

        Args:
            user_id: User ID

        Returns:
            List of (doc_id, Property) tuples
        """
        return self.query('createdBy', '==', user_id)

    def get_all_properties(self) -> List[tuple[str, Property]]:
        """
        Get all properties

        Returns:
            List of (doc_id, Property) tuples
        """
        return self.list_all()

    def update_property(self, property_id: str, property_model: Property) -> Property:
        """
        Update an existing property

        Args:
            property_id: Property ID string
            property_model: Updated Property model

        Returns:
            Updated Property model
        """
        return self.update(property_id, property_model)

    def delete_property(self, property_id: str) -> bool:
        """
        Delete a property

        Args:
            property_id: Property ID string

        Returns:
            True if deleted
        """
        return self.delete(property_id)

    def get_properties_by_status(self, status: str) -> List[tuple[str, Property]]:
        """
        Get properties by status

        Args:
            status: Property status

        Returns:
            List of (doc_id, Property) tuples
        """
        return self.query('status', '==', status)

    def search_properties(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        # 1. OPTIMIZATION: Narrow down initial fetch
        if filters.get("propertyType"):
            initial_results = self.query("propertyType", "==", filters["propertyType"])
        elif filters.get("listingType"):
            initial_results = self.query("listingType", "==", filters["listingType"])
        else:
            initial_results = self.list_all()

        matches = []

        for doc_id, prop in initial_results:
            # FIX 1: Keep this commented out for testing drafts
            # if prop.status != "published": continue 

            # --- A. Keyword Search (UPGRADED: Token-Based) ---
            if filters.get("keyword"):
                # 1. Clean the search term: lowercase and remove commas
                raw_keyword = filters["keyword"].lower().replace(",", " ")
                
                # 2. Split into individual words (tokens)
                # "Ermita, Cebu City" -> ["ermita", "cebu", "city"]
                search_tokens = raw_keyword.split()
                
                # 3. Build the text to search against
                searchable_text = f"{prop.name} {prop.address} {prop.description or ''} {prop.agentName or ''} {prop.developerName or ''}".lower()
                
                # 4. Check if ALL tokens are present in the text
                # This allows "Ermita Proper Cebu" to match "Ermita Cebu"
                if not all(token in searchable_text for token in search_tokens):
                    continue

            # --- B. Numeric Ranges ---
            if filters.get("minPrice") and prop.price < float(filters["minPrice"]):
                continue
            if filters.get("maxPrice") and prop.price > float(filters["maxPrice"]):
                continue
            if filters.get("bedrooms") and (prop.bedrooms is None or prop.bedrooms < float(filters["bedrooms"])):
                continue
            # Added safe check for bathrooms too just in case
            if filters.get("bathrooms") and (prop.bathrooms is None or prop.bathrooms < float(filters["bathrooms"])):
                continue

            if filters.get("storeys") and (prop.storeys is None or prop.storeys < float(filters["storeys"])):
                continue

            # --- C. Boolean Flags ---
            if filters.get("priceNegotiable") is True and not prop.priceNegotiable:
                continue
            if filters.get("parkingAvailable") is True and not prop.parkingAvailable:
                continue
            
            # --- D. Exact Matches (Enums) ---
            if filters.get("listingType") and prop.listingType != filters["listingType"]:
                continue
            if filters.get("propertyType") and prop.propertyType != filters["propertyType"]:
                continue
                
            # FIX 2: Smarter Pet Policy (Preserved from previous fix)
            if filters.get("petPolicy"):
                req_policy = filters["petPolicy"]
                prop_policy = prop.petPolicy or ""
                
                if req_policy == prop_policy:
                    pass 
                elif req_policy == "Pets allowed with restrictions" and "pets" in prop_policy.lower():
                    pass
                elif req_policy == "No pets allowed" and prop_policy != "No pets allowed":
                    continue
                elif req_policy == "Pets allowed" and prop_policy != "No pets allowed":
                    pass
                else:
                    if req_policy != prop_policy:
                        continue

            # --- E. Array Subsets (Preserved Fuzzy Match) ---
            if filters.get("amenities"):
                req_amenities = [a.lower() for a in filters["amenities"]]
                prop_amenities = [p.lower() for p in (prop.amenities or [])]
                
                missing_amenity = False
                for req in req_amenities:
                    found = False
                    for prop_am in prop_amenities:
                        if req in prop_am or prop_am in req:
                            found = True
                            break
                    if not found:
                        missing_amenity = True
                        break
                
                if missing_amenity:
                    continue
            
            # (Interior Features logic same as Amenities if needed...)

            # --- F. Serialize Result ---
            prop_dict = prop.to_dict()
            prop_dict["propertyId"] = doc_id 
            matches.append(prop_dict)

        return matches