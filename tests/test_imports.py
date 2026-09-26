import tempfile
import unittest
from pathlib import Path

from privatemoney.importers import parse_csv, parse_ofx
from privatemoney.state import FinanceState


class ImportTests(unittest.TestCase):
    def test_csv_parse_and_duplicate_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "statement.csv"
            path.write_text(
                "Date,Description,Amount\n"
                "09/20/2026,Coffee Shop,-5.25\n"
                "09/21/2026,Payroll,1000.00\n"
                "bad date,Broken Row,10.00\n",
                encoding="utf-8",
            )

            rows, skipped = parse_csv(
                path,
                date_col="Date",
                description_col="Description",
                amount_mode="single",
                amount_col="Amount",
            )
            self.assertEqual(len(rows), 2)
            self.assertEqual(skipped, 1)
            self.assertEqual(rows[0].merchant, "Coffee Shop")
            self.assertEqual(rows[0].amount_cents, -525)

            state = FinanceState()
            first = state.import_transactions("Checking", rows)
            second = state.import_transactions("Checking", rows)

            self.assertEqual(first["imported"], 2)
            self.assertEqual(first["duplicates"], 0)
            self.assertEqual(second["imported"], 0)
            self.assertEqual(second["duplicates"], 2)
            self.assertEqual(len(state.transactions()), 2)
            self.assertEqual(len(state.accounts()), 1)



    def test_separate_debit_credit_bank_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bank.csv"
            path.write_text(
                "Account,ChkRef,Debit,Credit,Balance,Date,Description\n"
                "1120883,,30,,103.54,9/23/2026,52723 POS PURCHASE TOTAL WIRELESS\n"
                "1120883,,16.5,,133.54,9/22/2026,72121 POS PURCHASE Waffle House 116 McMinnville TN\n",
                encoding="utf-8",
            )
            rows, skipped = parse_csv(
                path,
                date_col="Date",
                description_col="Description",
                amount_mode="split",
                debit_col="Debit",
                credit_col="Credit",
                account_col="Account",
                balance_col="Balance",
            )
            self.assertEqual(skipped, 0)
            self.assertEqual([r.amount_cents for r in rows], [-3000, -1650])
            self.assertEqual(rows[0].account_hint, "1120883")
            self.assertEqual(rows[0].balance_cents, 10354)

            state = FinanceState()
            result = state.import_transactions("", rows, use_account_column=True)
            self.assertEqual(result["imported"], 2)
            self.assertEqual(state.accounts()[0].name, "1120883")
            self.assertEqual(state.accounts()[0].current_balance, 103.54)

    def test_ofx_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "statement.ofx"
            path.write_text(
                """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252
COMPRESSION:NONE
OLDFILEUID:NONE
NEWFILEUID:NONE

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<STATUS><CODE>0<SEVERITY>INFO</STATUS>
<DTSERVER>20260926000000
<LANGUAGE>ENG
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<TRNUID>1
<STATUS><CODE>0<SEVERITY>INFO</STATUS>
<STMTRS>
<CURDEF>USD
<BANKACCTFROM>
<BANKID>000000000
<ACCTID>123456789
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20260901000000
<DTEND>20260926000000
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20260920120000
<TRNAMT>-5.25
<FITID>abc-123
<NAME>Coffee Shop
</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>100.00<DTASOF>20260926000000</LEDGERBAL>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
""",
                encoding="ascii",
            )

            rows, skipped = parse_ofx(path)
            self.assertEqual(skipped, 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].merchant, "Coffee Shop")
            self.assertEqual(rows[0].amount_cents, -525)
            self.assertEqual(rows[0].source, "ofx")
            self.assertEqual(rows[0].source_id, "abc-123")

    def test_invert_amounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "statement.csv"
            path.write_text(
                "date,description,amount\n"
                "2026-09-20,Purchase,12.50\n",
                encoding="utf-8",
            )
            rows, skipped = parse_csv(
                path,
                date_col="date",
                description_col="description",
                amount_mode="single",
                amount_col="amount",
                invert_amounts=True,
            )
            self.assertEqual(skipped, 0)
            self.assertEqual(rows[0].amount_cents, -1250)


if __name__ == "__main__":
    unittest.main()
