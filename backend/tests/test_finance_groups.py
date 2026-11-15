import unittest
from services.finance import FinanceError, calculate_tasks, prepare_entries


class GroupedTaskTests(unittest.TestCase):
    def setUp(self):
        self.devices = [{"id": i, "name": f"Vehicle {i:03}", "imei": f"IMEI{i}"} for i in range(1, 69)]
        self.task = {"category": "renewal", "total": "15000", "device_ids": list(range(1, 69)),
                     "pending_vehicles": [], "quantity": 68, "activity": "Annual renewal"}

    def test_68_vehicle_renewal_has_correct_quantity_and_totals(self):
        calculated = calculate_tasks([self.task])[0]
        self.assertEqual(calculated["quantity"], 68)
        self.assertEqual(calculated["total_minor"], 102000000)
        self.assertEqual([p["unit_amount_minor"] for p in calculated["breakdown"]], [1200000, 300000])
        self.assertEqual([p["amount_minor"] for p in calculated["breakdown"]], [81600000, 20400000])
        entries = prepare_entries([self.task], self.devices)
        self.assertEqual(len(entries), 68)
        self.assertEqual(sum(e["total_minor"] for e in entries), calculated["total_minor"])
        self.assertEqual({e["device"]["id"] for e in entries}, set(range(1, 69)))

    def test_pending_installation_minimum_is_per_vehicle(self):
        task = {"category": "installation", "total": "100000", "device_ids": [],
                "pending_vehicles": ["New Corolla", "New Hilux"], "quantity": 2}
        calculated = calculate_tasks([task])[0]
        self.assertEqual(calculated["total_minor"], 20000000)
        self.assertEqual(calculated["breakdown"][0]["amount_minor"], 2400000)
        self.assertEqual(calculated["breakdown"][1]["amount_minor"], 600000)
        entries = prepare_entries([task], [])
        self.assertEqual([e["vehicle_label"] for e in entries], ["New Corolla", "New Hilux"])
        self.assertTrue(all(e["link_status"] == "pending_installation" for e in entries))
        with self.assertRaises(FinanceError):
            prepare_entries([{**task, "total": "14999"}], [])

    def test_quantity_must_match_exact_list(self):
        for quantity in (67, 69, True, "68"):
            with self.subTest(quantity=quantity), self.assertRaises(FinanceError):
                prepare_entries([{**self.task, "quantity": quantity}], self.devices)

    def test_duplicate_selections_and_pending_labels_rejected(self):
        for changes in ({"device_ids": [1, 1]}, {"device_ids": [], "pending_vehicles": ["Corolla", " corolla "]}):
            raw = {**self.task, **changes}
            raw.pop("quantity")
            with self.assertRaises(FinanceError):
                prepare_entries([raw], self.devices)

    def test_duplicate_across_tasks_rejected_but_other_category_allowed(self):
        with self.assertRaises(FinanceError):
            prepare_entries([self.task, self.task], self.devices)
        entries = prepare_entries([self.task, {**self.task, "category": "maintenance"}], self.devices)
        self.assertEqual(len(entries), 136)

    def test_foreign_vehicle_rejected(self):
        with self.assertRaises(FinanceError):
            prepare_entries([{**self.task, "device_ids": [100], "quantity": 1}], self.devices)

    def test_empty_selection_calculates_zero_but_cannot_save(self):
        task = {**self.task, "device_ids": [], "quantity": 0}
        self.assertEqual(calculate_tasks([task])[0]["total_minor"], 0)
        with self.assertRaises(FinanceError):
            prepare_entries([task], self.devices)

    def test_legacy_single_vehicle_entries_still_work(self):
        entries = prepare_entries([{"category": "renewal", "total": "15000", "device_id": i} for i in range(1, 69)], self.devices)
        self.assertEqual(len(entries), 68)
        self.assertEqual(sum(e["total_minor"] for e in entries), 102000000)

    def test_invoice_quantity_and_amount_limits(self):
        with self.assertRaises(FinanceError):
            calculate_tasks([{**self.task, "device_ids": list(range(1, 1002)), "quantity": 1001}])
        with self.assertRaises(FinanceError):
            calculate_tasks([{**self.task, "total": "1000000000"}])


if __name__ == "__main__":
    unittest.main()
