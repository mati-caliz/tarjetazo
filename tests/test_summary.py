import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pdf_parser
from categorize import categorizar_movimientos
from formatter import formatear_resumen
from historico import periodo_anterior
from pdf_parser import Movimiento


class PdfParserTest(unittest.TestCase):
    @patch("pdf_parser._pagina1_texto")
    def test_extrae_cierre_y_vencimiento_actual(self, pagina1_texto) -> None:
        pagina1_texto.return_value = (
            "VENCIMIENTO ACTUAL: 24 Sep 26\n"
            "CIERRE ACTUAL: 10 Sep 26\n"
            "PROXIMO VTO 22 Oct 26"
        )

        self.assertEqual(pdf_parser.extraer_periodo(b"pdf", "clave"), "10 Sep 26")
        self.assertEqual(pdf_parser.extraer_vencimiento(b"pdf", "clave"), "24 Sep 26")

    @patch("pdf_parser._pagina1_texto")
    def test_extrae_vencimiento_de_tabla(self, pagina1_texto) -> None:
        pagina1_texto.return_value = (
            "CIERRE ACTUAL: 10 Sep 26 LIQ N030\n"
            "VENCIMIENTO SALDO $ SALDO U$S PAGO MIN. $ PAGO MIN. U$S\n"
            "23 Sep 26 540.526,97 5,30 100.000,00 --"
        )

        self.assertEqual(pdf_parser.extraer_vencimiento(b"pdf", "clave"), "23 Sep 26")


class CategorizeTest(unittest.TestCase):
    def test_reglas_corrigen_categorias_viejas_del_cache(self) -> None:
        conocidos = {
            "DIA TIENDA 316": {"nombre": "Dia Tienda 316", "categoria": "Otros"},
            "DeepSeek USD 5,30": {"nombre": "Deepseek", "categoria": "Otros"},
            "MERPAGO*TOSTADOBL": {"nombre": "Mercado Pago: Tostadobl", "categoria": "Otros"},
        }

        resultado = categorizar_movimientos(list(conocidos), conocidos)

        self.assertEqual(resultado["DIA TIENDA 316"]["categoria"], "Supermercado / Almacén")
        self.assertEqual(resultado["DeepSeek USD 5,30"]["categoria"], "IA / Herramientas digitales")
        self.assertEqual(resultado["MERPAGO*TOSTADOBL"]["categoria"], "Restaurantes / Bares")
        self.assertEqual(conocidos, resultado)

    def test_clasifica_comercios_e_impuestos_comunes(self) -> None:
        detalles = [
            "MERPAGO*PASSLINE",
            "MERPAGO*ACARREO1",
            "MERPAGO*CENIDOR C.05/06",
            "DB.RG 5617 30% ( 8021,55 )",
            "MERPAGO*GAUSSONLINE",
        ]

        with patch.dict("os.environ", {}, clear=True):
            resultado = categorizar_movimientos(detalles)

        self.assertEqual(resultado[detalles[0]]["categoria"], "Entretenimiento")
        self.assertEqual(resultado[detalles[1]]["categoria"], "Transporte")
        self.assertEqual(resultado[detalles[2]]["categoria"], "Indumentaria / Retail")
        self.assertEqual(resultado[detalles[3]]["categoria"], "Impuestos / Intereses")
        self.assertEqual(resultado[detalles[4]]["categoria"], "Tecnología / Electrónica")


class FormatterTest(unittest.TestCase):
    def test_destaca_vencimiento_y_mantiene_cierre(self) -> None:
        movimiento = Movimiento(datetime(2026, 9, 1), None, "DIA TIENDA 316", 100.0, 0.0)
        info = {
            movimiento.detalle: {
                "nombre": "Día",
                "categoria": "Supermercado / Almacén",
            }
        }

        mensaje = formatear_resumen([movimiento], info, "10 Sep 26", "24 Sep 26")

        self.assertTrue(mensaje.startswith("💳 <b>Resumen tarjeta BNA — vence 24 Sep 26</b>"))
        self.assertIn("Cierre: 10 Sep 26", mensaje)


class HistoryTest(unittest.TestCase):
    def test_reproceso_compara_con_periodo_anterior_real(self) -> None:
        historico = [{"periodo": "10 Ago 26"}, {"periodo": "10 Sep 26"}]

        anterior = periodo_anterior(historico, "10 Sep 26")

        self.assertEqual(anterior, {"periodo": "10 Ago 26"})


if __name__ == "__main__":
    unittest.main()
