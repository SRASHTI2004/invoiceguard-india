from app import gst
from app.money import inr, to_paise

BUYER = gst.make_gstin("29", "AABCB5521M")      # Karnataka buyer
SUP_KA = gst.make_gstin("29", "AAACN4821K")     # Karnataka supplier
SUP_MH = gst.make_gstin("27", "AAACP7712D")     # Maharashtra supplier


def invoice(**over):
    """A valid intra-state invoice: Rs 10,000 taxable at 18% -> CGST 900 + SGST 900 = 11,800."""
    inv = {
        "supplier_gstin": SUP_KA, "buyer_gstin": BUYER, "place_of_supply": "29-Karnataka",
        "line_items": [{"description": "Laptop stand", "hsn": "9403", "qty": 10, "unit_paise": 100000, "gst_rate": 18}],
        "taxable_paise": 1000000, "cgst_paise": 90000, "sgst_paise": 90000, "igst_paise": 0, "total_paise": 1180000,
    }
    inv.update(over)
    return inv


def failed(inv, saved=None):
    return {r.code for r in gst.run_gst_checks(inv, BUYER, saved) if not r.ok}


# ---- money -------------------------------------------------------------------------------------------------------
def test_indian_number_formatting():
    assert inr(0) == "₹0.00"
    assert inr(99) == "₹0.99"
    assert inr(100000) == "₹1,000.00"
    assert inr(1000000) == "₹10,000.00"
    assert inr(12400000) == "₹1,24,000.00"
    assert inr(123456789) == "₹12,34,567.89"
    assert inr(1000000000) == "₹1,00,00,000.00"
    assert inr(-5000000) == "-₹50,000.00"


def test_to_paise_rounds_half_up_and_rejects_junk():
    assert to_paise(1240) == 124000
    assert to_paise("99.995") == 10000
    assert to_paise(None) is None and to_paise("abc") is None and to_paise(True) is None


# ---- GSTIN -------------------------------------------------------------------------------------------------------
def test_known_real_gstin_passes_the_check_character():
    ok, _ = gst.validate_gstin("27AAPFU0939F1ZV")  # widely published example GSTIN
    assert ok


def test_generated_gstins_are_valid():
    assert gst.validate_gstin(SUP_KA)[0] and gst.validate_gstin(SUP_MH)[0]


def test_wrong_check_character_is_rejected():
    fake = SUP_KA[:14] + ("A" if SUP_KA[14] != "A" else "B")
    ok, why = gst.validate_gstin(fake)
    assert not ok and "check character" in why


def test_bad_format_and_state_code_are_rejected():
    assert not gst.validate_gstin("29AAACN4821K1Z")[0]          # 14 chars
    assert not gst.validate_gstin("29aaacn4821k1zx"[:3] + "!")[0]
    assert not gst.validate_gstin("")[0] and not gst.validate_gstin(None)[0]
    bad_state = gst.make_gstin("28", "AAACN4821K")              # 28 is not a current state code
    ok, why = gst.validate_gstin(bad_state)
    assert not ok and "state code" in why


def test_gstin_is_case_and_space_tolerant():
    assert gst.validate_gstin(f" {SUP_KA.lower()} ")[0]


def test_place_of_supply_parsing():
    assert gst.parse_place_of_supply("29-Karnataka") == "29"
    assert gst.parse_place_of_supply("Karnataka (29)") == "29"
    assert gst.parse_place_of_supply("Maharashtra") == "27"
    assert gst.parse_place_of_supply("Jammu & Kashmir") == "01"
    assert gst.parse_place_of_supply("Mars") is None and gst.parse_place_of_supply(None) is None


# ---- a clean invoice ---------------------------------------------------------------------------------------------
def test_valid_intra_state_invoice_passes_everything():
    assert failed(invoice()) == set()


def test_valid_inter_state_invoice_passes_everything():
    inv = invoice(supplier_gstin=SUP_MH, cgst_paise=0, sgst_paise=0, igst_paise=180000)
    assert failed(inv) == set()


# ---- tax type ----------------------------------------------------------------------------------------------------
def test_igst_charged_within_the_same_state_is_wrong_tax_type():
    inv = invoice(cgst_paise=0, sgst_paise=0, igst_paise=180000)
    assert failed(inv) == {"wrong_tax_type"}


def test_cgst_sgst_charged_across_states_is_wrong_tax_type():
    assert failed(invoice(supplier_gstin=SUP_MH)) == {"wrong_tax_type"}


def test_unknown_place_of_supply_fails():
    assert "place_of_supply_unknown" in failed(invoice(place_of_supply="Atlantis"))


# ---- arithmetic --------------------------------------------------------------------------------------------------
def test_wrong_gst_total_is_caught():
    assert failed(invoice(total_paise=1280000)) == {"gst_total_wrong"}


def test_understated_gst_amount_is_caught():
    inv = invoice(cgst_paise=45000, sgst_paise=45000, total_paise=1090000)
    assert "gst_amount_wrong" in failed(inv)


def test_unequal_cgst_sgst_is_caught():
    assert "cgst_sgst_unequal" in failed(invoice(cgst_paise=120000, sgst_paise=60000))


def test_taxable_value_must_match_line_items():
    assert "taxable_mismatch" in failed(invoice(taxable_paise=1100000))


def test_rounding_within_one_rupee_is_tolerated():
    assert failed(invoice(cgst_paise=90050, sgst_paise=90050, total_paise=1180100)) == set()


def test_mixed_rates_use_each_lines_own_rate():
    items = [{"description": "A", "hsn": "4820", "qty": 1, "unit_paise": 100000, "gst_rate": 12},
             {"description": "B", "hsn": "998313", "qty": 1, "unit_paise": 100000, "gst_rate": 18}]
    assert gst.expected_tax_paise(items) == 30000
    inv = invoice(line_items=items, taxable_paise=200000, cgst_paise=15000, sgst_paise=15000, total_paise=230000)
    assert failed(inv) == set()


def test_invalid_gst_slab_is_caught():
    inv = invoice()
    inv["line_items"][0]["gst_rate"] = 17
    assert "gst_rate_invalid" in failed(inv)


def test_unreadable_line_items_fail_instead_of_crashing():
    assert "gst_arithmetic" in failed(invoice(line_items=[{"description": "x", "qty": None, "unit_paise": 5}]))
    assert "gst_arithmetic" in failed(invoice(line_items=[]))


# ---- HSN / SAC ---------------------------------------------------------------------------------------------------
def test_hsn_and_sac_formats():
    inv = invoice()
    for good in ("9403", "940360", "94036090", "998313"):
        inv["line_items"][0]["hsn"] = good
        assert "hsn_invalid" not in failed(inv)
    for bad in (None, "", "94", "94031", "ABCD", "99831"):
        inv["line_items"][0]["hsn"] = bad
        assert "hsn_invalid" in failed(inv)


# ---- GSTINs on the invoice ---------------------------------------------------------------------------------------
def test_fake_supplier_gstin_is_a_block_level_failure():
    fake = SUP_KA[:14] + ("A" if SUP_KA[14] != "A" else "B")
    results = gst.run_gst_checks(invoice(supplier_gstin=fake), BUYER)
    bad = [r for r in results if r.code == "supplier_gstin_invalid"][0]
    assert not bad.ok and bad.severity == gst.BLOCK


def test_gstin_must_match_the_saved_supplier():
    other = gst.make_gstin("29", "AAACZ9999Z")
    assert failed(invoice(), saved=other) == {"supplier_gstin_mismatch"}
    assert failed(invoice(), saved=SUP_KA) == set()


def test_invoice_billed_to_someone_elses_gstin():
    other_buyer = gst.make_gstin("29", "AAACZ9999Z")
    assert failed(invoice(buyer_gstin=other_buyer)) == {"buyer_gstin_mismatch"}
    assert failed(invoice(buyer_gstin=None)) == {"buyer_gstin_mismatch"}


def test_report_serialises_for_the_dashboard():
    rows = [r.as_dict() for r in gst.run_gst_checks(invoice(total_paise=1280000), BUYER)]
    assert all({"code", "label", "ok", "message", "severity"} <= set(r) for r in rows)
    assert [r for r in rows if not r["ok"]][0]["severity"] == "HOLD"
