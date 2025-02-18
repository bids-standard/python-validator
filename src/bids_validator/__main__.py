
from bids_validator import BIDSValidator
import typer

validator = BIDSValidator()

app = typer.Typer()

@app.command()
def main(bids_path: str):

    if not validator.is_bids(bids_path):
        print(f"{bids_path} is not a valid bids filename")

if __name__ == '__main__':
    app()