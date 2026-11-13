import unittest

from run_local import local_database_url


class LocalStartupTests(unittest.TestCase):
    def test_replaces_only_host_port_preserving_encoded_credentials(self):
        source = "mysql+pymysql://reader:example%40pass%3Aword@mysql57:3306/traccar?charset=utf8mb4"
        url = local_database_url(source)
        self.assertEqual(url.host, "127.0.0.1")
        self.assertEqual(url.port, 13306)
        self.assertEqual(url.username, "reader")
        self.assertEqual(url.password, "example@pass:word")
        self.assertEqual(url.database, "traccar")
        self.assertEqual(url.query["charset"], "utf8mb4")
        self.assertEqual(local_database_url(url.render_as_string(hide_password=False)), url)

    def test_custom_tunnel_port(self):
        self.assertEqual(local_database_url("mysql+pymysql://reader:example@mysql57/traccar", 13307).port, 13307)

    def test_rejects_alternative_connection_targets(self):
        for source in ("sqlite:///:memory:", "mysql+pymysql://reader:example@mysql57/traccar?unix_socket=/tmp/mysql.sock"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                local_database_url(source)


if __name__ == "__main__":
    unittest.main()
