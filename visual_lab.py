import datetime
import json
import os
import re
import shutil
import sys
from typing import Dict

import requests
from blessed import Terminal
from bs4 import BeautifulSoup

TERM = Terminal()


class VisualLab:
    def __init__(self, *args, **kwargs):

        self.session = requests.Session()
        self.base_url = "http://visual.ic.uff.br/dmi"

        with open("settings.json", "r") as f:
            self.settings = json.load(f)

        self.data_path = "data"
        if self.settings["clear_data_beforehand"] is True:
            shutil.rmtree(self.data_path, ignore_errors=True)
        os.makedirs(self.data_path, exist_ok=True)

        self.log_path = "report.log"
        with open(self.log_path, "w") as fp:
            fp.write("")

        self.total = 0
        self.progress = 1
        self.errors = 0

        self.current_id = None

    def run(self) -> None:
        if not self._login():
            print("Username or password is incorrect.")
            sys.exit()

        patients = self._get_patients()
        self.total = len(patients.keys())

        classes_path = self._get_classes_path(patients)

        global_id = None
        for id_, class_ in patients.items():
            self._print_progress()

            self.current_id = id_

            patient_path = f"{classes_path[class_]}/{id_}"
            os.makedirs(patient_path, exist_ok=True)

            url = f"http://visual.ic.uff.br/dmi/prontuario/details.php?id={id_}"
            resp = self.session.get(url)
            bs = BeautifulSoup(resp.text, "lxml")

            if self.settings["save_record_page"] is True:
                with open(f"{patient_path}/record.html", "w") as fp:
                    fp.write(resp.text)

            if self.settings["save_images"] is True:
                self._download_patient_images(bs, patient_path)

            if self.settings["save_thermal_matrixes"] is True:
                self._download_patient_matrixes(bs, patient_path)

    def _print_progress(self) -> None:
        print(TERM.clear)
        print(f"Processing {self.progress} of {self.total}")
        print(f"{self.errors} errors. Check 'report.log' for details.")

        self.progress += 1

    def _append_error(self, error: Exception, filename: str) -> None:
        line = f"{datetime.datetime.now().isoformat()} - failed to download '{filename}' at patitent #'{self.current_id}' - {str(error)}\n"
        with open(self.log_path, "a+") as fp:
            fp.write(line)

    def _login(self) -> bool:
        url = "http://visual.ic.uff.br/dmi/"
        self.session.head(url)

        payload = {
            "usuario": self.settings["login"]["username"],
            "password": self.settings["login"]["password"],
        }
        url = "http://visual.ic.uff.br/dmi/login.php"
        resp = self.session.post(url, data=payload)

        return not BeautifulSoup(resp.text, "lxml").find(class_="alert-warning")

    def _get_patients(self) -> Dict[str, str]:
        ids = []
        diags = []
        pagina = 1

        while True:
            url = f"http://visual.ic.uff.br/dmi/prontuario/index.php?diag=&filtro=0&order=1&by=1&pagina={pagina}"
            resp = self.session.get(url)
            bs = BeautifulSoup(resp.text, "lxml")

            trs = bs.find(id="mytable").find_all("tr")[1:]
            ids += [tr.td.text for tr in trs]
            diags += [tr.find_all("td")[5].text for tr in trs]

            pagination = bs.find(class_="pagination").text
            if "next" in pagination.lower():
                pagina += 1
            else:
                break

        return dict(zip(ids, diags))

    def _get_classes_path(self, patients: dict) -> Dict[str, str]:
        classes = list(set(patients.values()))
        classes_path = dict()
        for class_ in classes:
            classes_path[class_] = f"{self.data_path}/{class_}"
            os.makedirs(classes_path[class_], exist_ok=True)
        return classes_path

    def _download_patient_images(
        self, record_page: BeautifulSoup, patient_path: str
    ) -> None:
        images_path = f"{patient_path}/images"
        os.makedirs(images_path, exist_ok=True)

        images = record_page.find_all(class_="imagem")

        for image in images:
            filename = None
            try:
                href = image.find(class_="botoes").find_all("a")[2]["href"]
                href = self.base_url + href[2:]
                filename = re.search(r".*/(.*)$", href).group(1)
                file = self.session.get(href, stream=True)

                with open(f"{images_path}/{filename}", "wb") as fp:
                    fp.write(file.content)
            except Exception as err:
                self._append_error(err, filename)

    def _download_patient_matrixes(
        self, record_page: BeautifulSoup, patient_path: str
    ) -> None:
        static_path = f"{patient_path}/Static"
        dynamic_path = f"{patient_path}/Dynamic"
        os.makedirs(static_path, exist_ok=True)
        os.makedirs(dynamic_path, exist_ok=True)

        div = record_page.find(
            "h4", text=re.compile(r"thermal", re.I)
        ).next_sibling.next_sibling
        links = div.find_all("a")
        matrixes = [
            {
                "url": self.base_url + link["href"][2:],
                "path": static_path
                if "static" in link["title"].lower()
                else dynamic_path,
            }
            for link in links
        ]
        for matrix in matrixes:
            filename = None
            try:
                path = matrix["path"]
                filename = re.search(r".*/(.*)$", matrix["url"]).group(1)
                file = self.session.get(matrix["url"], stream=True)

                with open(f"{path}/{filename}", "w") as fp:
                    fp.write(file.text)
            except Exception as err:
                self._append_error(err, filename)


if __name__ == "__main__":
    print(TERM.clear)
    VisualLab().run()
