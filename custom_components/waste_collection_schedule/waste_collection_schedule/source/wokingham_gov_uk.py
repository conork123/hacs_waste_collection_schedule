from datetime import datetime

import requests
from bs4 import BeautifulSoup
from waste_collection_schedule import Collection  # type: ignore[attr-defined]

TITLE = "Wokingham Borough Council"
DESCRIPTION = "Source for wokingham.gov.uk services for Wokingham, UK."
URL = "https://wokingham.gov.uk"
API_URL = "https://www.wokingham.gov.uk/rubbish-and-recycling/waste-collection/see-your-new-bin-collection-dates"
TEST_CASES = {
    "Test_001": {"postcode": "RG40 1GE", "property": "92923"},
    "Test_002": {"postcode": "RG413BP", "property": "111744"},
    "Test_003": {"postcode": "rg41 1ph", "property": 108604},
    "Test_004": {"postcode": "RG40 2LW", "address": "16 Davy Close"},
}
ICON_MAP = {
    "HOUSEHOLD WASTE": "mdi:trash-can",
    "GARDEN WASTE": "mdi:leaf",
    "RECYCLING": "mdi:recycle",
    "FOOD WASTE": "mdi:food",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/117.0",
    "Content-Type": "application/x-www-form-urlencoded",
    "Host": "www.wokingham.gov.uk",
    "Origin": "https://www.wokingham.gov.uk",
    "Referer": "https://www.wokingham.gov.uk/rubbish-and-recycling/waste-collection/see-your-new-bin-collection-dates",
}


class Source:
    def __init__(self, postcode=None, property=None, address=None):
        self._postcode = postcode
        self._property = property
        self._address = address

    def get_form_id(self, txt: str) -> str:
        soup = BeautifulSoup(txt, "html.parser")
        x = soup.find("input", {"name": "form_build_id"})
        id = x.get("value")
        return id

    def match_address(self, lst: list, addr: str) -> str:
        for item in lst:
            if addr in item.text.replace(",", ""):
                a = item.get("value")
        return a

    def fetch(self):
        s = requests.Session()

        # Load page to generate token needed for subsequent query
        r = s.get(API_URL)
        form_id = self.get_form_id(r.text)

        # Perform postcode search to generate token needed for following query
        self._postcode = str(self._postcode.upper().strip().replace(" ", ""))
        payload = {
            "postcode_search_csv": self._postcode,
            "op": "Find Address",
            "form_build_id": form_id,
            "form_id": "waste_recycling_information",
        }
        r = s.post(
            API_URL,
            headers=HEADERS,
            data=payload,
        )
        form_id = self.get_form_id(r.text)

        # Use address to get an ID if property wasn't supplied. Assumes first match is correct.
        if self._property is None:
            soup = BeautifulSoup(r.text, "html.parser")
            dropdown = soup.find("div", {"class": "form-item__dropdown"})
            addresses = dropdown.find_all("option")
            self._address = self._address.upper()
            self._property = self.match_address(addresses, self._address)
        else:
            self._property = str(self._property)

        # Now get the collection schedule
        payload = {
            "postcode_search_csv": self._postcode,
            "address_options_csv": self._property,
            "op": "Show collection dates",
            "form_build_id": form_id,
            "form_id": "waste_recycling_information",
        }
        r = s.post(
            API_URL,
            headers=HEADERS,
            data=payload,
        )
        soup = BeautifulSoup(r.text, "html.parser")

        entries = []

        # check for changed Christmas & New Year collections messages
        christmas = soup.find_all(
            "div", {"class": "waste-collection-information__christmas"}
        )
        if christmas:  # just process info on changed collections
            changes = christmas[0].find_all("p")
            for change in changes:
                span = change.find("span")
                if span:
                    waste_type = (
                        span.get_text(strip=True)
                        .replace("Changes to ", "")
                        .replace(":", "")
                    )
                    waste_dates = [
                        date.strip()
                        for date in change.get_text()
                        .replace(".", "")
                        .split("The new collection date will be ")[1:]
                    ]
                    for waste_date in waste_dates:
                        entries.append(
                            Collection(
                                date=datetime.strptime(
                                    waste_date, "%A %d/%m/%Y"
                                ).date(),
                                t=f"{waste_type} (Christmas Schedule)",
                                icon=ICON_MAP.get(waste_type.upper()),
                            )
                        )
        else:  # process info on regular collections
            cards = soup.find_all("div", {"class": "card--waste"})
            # Extract the collection schedules
            for card in cards:
                # Cope with Garden waste suffixed with (week 1) or (week 2)
                waste_type = " ".join(card.find("h3").text.strip().split()[:2])
                waste_date = card.find("span").text.strip().split()[-1]
                entries.append(
                    Collection(
                        date=datetime.strptime(waste_date, "%d/%m/%Y").date(),
                        t=waste_type,
                        icon=ICON_MAP.get(waste_type.upper()),
                    )
                )

        return entries
