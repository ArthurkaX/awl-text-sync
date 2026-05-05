from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from awl_text_sync.builder import build_monolith, build_patch, build_split_import
from awl_text_sync.config import resolve_workspace
from awl_text_sync.call_graph import build_call_graph, default_call_graph_report_path, write_call_graph_report
from awl_text_sync.models import Block, slugify_symbol_name
from awl_text_sync.parser import ParseError
from awl_text_sync.splitter import split_exported_workspace
from awl_text_sync.validator import validate_workspace


NUMERIC_MONOLITH = """TYPE UDT 1271
TITLE =
VERSION : 0.1
  STRUCT
   Field : INT ;
  END_STRUCT ;
END_TYPE

FUNCTION_BLOCK FB 68
TITLE =
VERSION : 0.1
NAME : STD_DEVIATION
BEGIN
NETWORK
TITLE =
END_FUNCTION_BLOCK

FUNCTION FC 100 : VOID
TITLE =
VERSION : 0.1
BEGIN
NETWORK
TITLE =
END_FUNCTION

DATA_BLOCK DB 1
TITLE =
VERSION : 0.1
BEGIN
END_DATA_BLOCK

ORGANIZATION_BLOCK OB 1
TITLE =
VERSION : 0.1
BEGIN
NETWORK
TITLE =
END_ORGANIZATION_BLOCK
"""


SYMBOLIC_MONOLITH = """TYPE "UDT_HMI_Menu_Note_ID"
TITLE =
VERSION : 0.1
  STRUCT
   Field : INT ;
  END_STRUCT ;
END_TYPE

FUNCTION_BLOCK "FB_Std_Deviation"
TITLE =
VERSION : 0.1
BEGIN
NETWORK
TITLE =
END_FUNCTION_BLOCK

FUNCTION "FC_Force_Inputs" : VOID
TITLE =
VERSION : 0.1
NAME : FORCE_INPUTS
BEGIN
NETWORK
TITLE =
END_FUNCTION

DATA_BLOCK "DB_Dummy"
TITLE =
VERSION : 0.1
BEGIN
END_DATA_BLOCK

ORGANIZATION_BLOCK "OB_Program_Cycle"
TITLE =
VERSION : 0.1
BEGIN
NETWORK
TITLE =
END_ORGANIZATION_BLOCK
"""


SYMBOLS_SDF = "\r\n".join(
    [
        '"UDT_HMI_Menu_Note_ID    ","UDT  1271   ","UDT  1271 ","GEN:                                                                            "',
        '"FB_Std_Deviation        ","FB     68   ","FB     68 ","GEN:                                                                            "',
        '"FC_Force_Inputs         ","FC    100   ","FC    100 ","GEN:                                                                            "',
        '"DB_Dummy                ","DB      1   ","DB      1 ","GEN:                                                                            "',
        '"OB_Program_Cycle        ","OB      1   ","OB      1 ","GEN:                                                                            "',
        "",
    ]
)


STL_VALIDATE_MONOLITH = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Value : INT ;
END_VAR
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 100
TITLE =
NAME : WORKER
VERSION : 0.1
VAR_INPUT
  i_Value : INT ;
END_VAR
BEGIN
END_FUNCTION_BLOCK

DATA_BLOCK DB 100
TITLE =
NAME : HELPER_DATA
VERSION : 0.1
BEGIN
END_DATA_BLOCK

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
VAR
  s_Helper : FB 100;
END_VAR
VAR_TEMP
  t_Value : INT;
END_VAR
BEGIN
NETWORK
TITLE =
      CALL FB 100 , DB 100 (
           i_Value := #t_Value);
DA01: NOP   0;
TA15: =     M 0.0;
      CALL #s_Helper (
           i_Value := #t_Value);
      JU    DA01;
END_FUNCTION_BLOCK
"""


QUOTED_INSTANCE_MONOLITH = """FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
VAR
  s_FB_TCON : "TCON";
END_VAR
VAR_INPUT
  i_Enable_Conn : BOOL;
END_VAR
BEGIN
NETWORK
TITLE =
      CALL #s_FB_TCON (
           REQ := #i_Enable_Conn);
END_FUNCTION_BLOCK
"""


class NamingTests(unittest.TestCase):
    def test_slugify_symbol_name(self) -> None:
        self.assertEqual(slugify_symbol_name("FB_Std_Deviation"), "std_deviation")
        self.assertEqual(slugify_symbol_name("OB Program Cycle"), "program_cycle")
        self.assertEqual(slugify_symbol_name("UDT-HMI Menu Note ID"), "hmi_menu_note_id")

    def test_block_filename_prefers_symbol_suffix(self) -> None:
        block = Block(block_type="FB", number=68, source="", symbol_name="FB_Std_Deviation")
        self.assertEqual(block.filename, "fb68_FB_Std_Deviation.awl")

    def test_block_filename_uses_internal_name_when_symbol_missing(self) -> None:
        block = Block(block_type="FB", number=1, source="", internal_name="SORTER")
        self.assertEqual(block.filename, "fb1_SORTER.awl")


class WorkspaceSplitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.test_root = Path("tests") / ".tmp" / uuid4().hex
        self.test_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.test_root, ignore_errors=True)

    def _write_workspace(self, tmp: str, monolith_name: str, monolith_text: str, symbols_text: str = SYMBOLS_SDF) -> Path:
        root = Path(tmp)
        exported = root / "Exported"
        exported.mkdir(parents=True, exist_ok=True)
        (exported / monolith_name).write_text(monolith_text.replace("\n", "\r\n"), encoding="cp1252")
        (exported / "whatever_symbols.sdf").write_text(symbols_text, encoding="cp1252", newline="")
        return root

    def test_split_numeric_export_uses_symbol_suffixes(self) -> None:
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH)
        paths = resolve_workspace(root)
        count = split_exported_workspace(paths)
        self.assertEqual(count, 5)
        self.assertEqual(
            (root / ".gitignore").read_text(encoding="utf-8"),
            "*\n!.gitignore\n!Project/\n!Project/**\n",
        )
        self.assertTrue((paths.project_blocks_dir / "udt1271_UDT_HMI_Menu_Note_ID.awl").exists())
        self.assertTrue((paths.project_blocks_dir / "fb68_FB_Std_Deviation.awl").exists())
        self.assertTrue((paths.project_blocks_dir / "fc100_FC_Force_Inputs.awl").exists())
        self.assertTrue((paths.project_blocks_dir / "db1_DB_Dummy.awl").exists())
        self.assertTrue((paths.project_blocks_dir / "ob1_OB_Program_Cycle.awl").exists())
        self.assertTrue((root / "docs" / "working_rules.md").exists())
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 5)

    def test_split_creates_rules_file_when_missing(self) -> None:
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH)
        paths = resolve_workspace(root)
        split_exported_workspace(paths)

        rules_path = root / "docs" / "working_rules.md"
        self.assertTrue(rules_path.exists())
        rules_text = rules_path.read_text(encoding="utf-8")
        self.assertIn("# Rules For Editing This Project", rules_text)
        self.assertIn("Project/Blocks", rules_text)

    def test_split_does_not_overwrite_existing_rules_file(self) -> None:
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH)
        rules_path = root / "docs" / "working_rules.md"
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text("custom rules\n", encoding="utf-8", newline="")

        paths = resolve_workspace(root)
        split_exported_workspace(paths)

        self.assertEqual(rules_path.read_text(encoding="utf-8"), "custom rules\n")

    def test_split_symbolic_export_resolves_numbers_via_symbols(self) -> None:
        root = self._write_workspace(str(self.test_root), "symbols_mode_export.AWL", SYMBOLIC_MONOLITH)
        paths = resolve_workspace(root)
        count = split_exported_workspace(paths)
        self.assertEqual(count, 5)
        self.assertTrue((paths.project_blocks_dir / "udt1271_UDT_HMI_Menu_Note_ID.awl").exists())
        self.assertTrue((paths.project_blocks_dir / "fb68_FB_Std_Deviation.awl").exists())
        self.assertTrue((paths.project_blocks_dir / "fc100_FC_Force_Inputs.awl").exists())
        self.assertTrue((paths.project_blocks_dir / "db1_DB_Dummy.awl").exists())
        self.assertTrue((paths.project_blocks_dir / "ob1_OB_Program_Cycle.awl").exists())
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 5)

    def test_split_normalizes_symbols_to_utf8_in_project(self) -> None:
        symbols = '"OB_Program_Cycle        ","OB      1   ","OB      1 ","Temp °C                                                                        "\r\n'
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH, symbols_text=symbols)
        paths = resolve_workspace(root)
        split_exported_workspace(paths)

        project_symbols = next(paths.project_symbols_dir.glob("*.sdf"))
        self.assertIn("°C", project_symbols.read_text(encoding="utf-8"))

    def test_split_accepts_indented_block_headers(self) -> None:
        monolith = NUMERIC_MONOLITH.replace("ORGANIZATION_BLOCK OB 1", "      ORGANIZATION_BLOCK OB 1")
        root = self._write_workspace(str(self.test_root), "indented_export.awl", monolith)
        paths = resolve_workspace(root)
        count = split_exported_workspace(paths)
        self.assertEqual(count, 5)
        self.assertTrue((paths.project_blocks_dir / "ob1_OB_Program_Cycle.awl").exists())

    def test_split_replaces_legacy_filename_for_same_block(self) -> None:
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH)
        legacy = root / "Project" / "Blocks" / "db1_dummy.awl"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text("legacy\n", encoding="utf-8", newline="")

        paths = resolve_workspace(root)
        split_exported_workspace(paths)

        self.assertTrue((paths.project_blocks_dir / "db1_DB_Dummy.awl").exists())

    def test_split_rejects_multiple_awl_files(self) -> None:
        root = self._write_workspace(str(self.test_root), "first.awl", NUMERIC_MONOLITH)
        exported = root / "Exported"
        (exported / "second.AWL").write_text(NUMERIC_MONOLITH.replace("\n", "\r\n"), encoding="cp1252")
        paths = resolve_workspace(root)
        with self.assertRaisesRegex(FileExistsError, r"Multiple monolith export files"):
            split_exported_workspace(paths)

    def test_split_rejects_multiple_sdf_files(self) -> None:
        root = self._write_workspace(str(self.test_root), "first.awl", NUMERIC_MONOLITH)
        exported = root / "Exported"
        (exported / "second_symbols.SDF").write_text(SYMBOLS_SDF, encoding="cp1252", newline="")
        paths = resolve_workspace(root)
        with self.assertRaisesRegex(FileExistsError, r"Multiple symbols export files"):
            split_exported_workspace(paths)

    def test_build_monolith_writes_cp1252_for_step7_import(self) -> None:
        symbols = '"FC_HELPER                ","FC    100   ","FC    100 ","GEN:                                                                            "\r\n'
        root = self._write_workspace(
            str(self.test_root),
            "fc_export.awl",
            """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      // value
END_FUNCTION
""",
            symbols_text=symbols,
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        block_path = paths.project_blocks_dir / "fc100_FC_HELPER.awl"
        block_path.write_text(
            block_path.read_text(encoding="utf-8").replace("// value", "// value °C"),
            encoding="utf-8",
            newline="",
        )

        count = build_monolith(paths)

        self.assertEqual(count, 1)
        self.assertIn("value °C", paths.build_all_blocks.read_text(encoding="cp1252"))

    def test_build_split_writes_cp1252_for_step7_import(self) -> None:
        symbols = '"OB_Program_Cycle        ","OB      1   ","OB      1 ","Temp °C                                                                        "\r\n'
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH, symbols_text=symbols)
        paths = resolve_workspace(root)
        split_exported_workspace(paths)

        count = build_split_import(paths)

        self.assertEqual(count, 5)
        split_block = paths.build_split_blocks_dir / "ob1_OB_Program_Cycle.awl"
        self.assertIn("ORGANIZATION_BLOCK OB 1", split_block.read_text(encoding="cp1252"))
        split_symbols = next(paths.build_split_symbols_dir.glob("*.sdf"))
        self.assertIn("°C", split_symbols.read_text(encoding="cp1252"))

    def test_build_patch_writes_only_changed_blocks(self) -> None:
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH)
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        block_path = paths.project_blocks_dir / "fc100_FC_Force_Inputs.awl"
        block_path.write_text(
            block_path.read_text(encoding="utf-8").replace("END_FUNCTION", "      // patched\nEND_FUNCTION"),
            encoding="utf-8",
            newline="",
        )

        count = build_patch(paths)

        self.assertEqual(count, 1)
        patch_text = paths.build_patch_blocks.read_text(encoding="cp1252")
        self.assertIn("FUNCTION FC 100 : VOID", patch_text)
        self.assertIn("// patched", patch_text)
        self.assertNotIn("FUNCTION_BLOCK FB 68", patch_text)
        self.assertNotIn("ORGANIZATION_BLOCK OB 1", patch_text)

    def test_build_patch_writes_empty_file_when_no_blocks_changed(self) -> None:
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH)
        paths = resolve_workspace(root)
        split_exported_workspace(paths)

        count = build_patch(paths)

        self.assertEqual(count, 0)
        self.assertEqual(paths.build_patch_blocks.read_text(encoding="cp1252"), "")

    def test_build_patch_includes_new_blocks(self) -> None:
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH)
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        (paths.project_blocks_dir / "fc101.awl").write_text(
            """FUNCTION FC 101 : VOID
TITLE =
VERSION : 0.1
BEGIN
END_FUNCTION
""",
            encoding="utf-8",
            newline="",
        )

        count = build_patch(paths)

        self.assertEqual(count, 1)
        patch_text = paths.build_patch_blocks.read_text(encoding="cp1252")
        self.assertIn("FUNCTION FC 101 : VOID", patch_text)
        self.assertNotIn("FUNCTION FC 100 : VOID", patch_text)

    def test_validate_rejects_non_cp1252_characters_before_build(self) -> None:
        symbols = '"FC_HELPER                ","FC    100   ","FC    100 ","GEN:                                                                            "\r\n'
        root = self._write_workspace(
            str(self.test_root),
            "fc_export.awl",
            """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      // value
END_FUNCTION
""",
            symbols_text=symbols,
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        block_path = paths.project_blocks_dir / "fc100_FC_HELPER.awl"
        block_path.write_text(
            block_path.read_text(encoding="utf-8").replace("// value", "// valueⁿ"),
            encoding="utf-8",
            newline="",
        )

        with self.assertRaisesRegex(ParseError, r"not representable in cp1252"):
            validate_workspace(paths)

    def test_validate_rejects_suspicious_mojibake(self) -> None:
        root = self._write_workspace(str(self.test_root), "my_export.awl", NUMERIC_MONOLITH)
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        block_path = paths.project_blocks_dir / "db1_DB_Dummy.awl"
        block_path.write_text(
            block_path.read_text(encoding="utf-8").replace("BEGIN", "BEGIN\r\n// ┬░C"),
            encoding="utf-8",
            newline="",
        )

        with self.assertRaisesRegex(ParseError, r"suspicious mojibake"):
            validate_workspace(paths)

    def test_validate_accepts_split_workspace_when_internal_name_disagrees(self) -> None:
        root = self._write_workspace(str(self.test_root), "fb_export.awl", """FUNCTION_BLOCK FB 1
TITLE =%version: 0.1 % CN: 30
FAMILY : PROCESS
NAME : SORTER
VERSION : 0.1
BEGIN
NETWORK
TITLE =
END_FUNCTION_BLOCK
""")
        exported = root / "Exported"
        (exported / "whatever_symbols.sdf").write_text(
            '"FB_CONVEYOR              ","FB      1   ","FB      1 ","GEN:                                                                            "\r\n',
            encoding="cp1252",
            newline="",
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 1)

    def test_validate_accepts_consistent_db_access_styles(self) -> None:
        symbols = '"FB_SORTER                ","FB      1   ","FB      1 ","GEN:                                                                            "\r\n'
        root = self._write_workspace(
            str(self.test_root),
            "fb_export.awl",
            """FUNCTION_BLOCK FB 1
TITLE =%version: 0.1 % CN: 30
FAMILY : PROCESS
NAME : SORTER
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      L     DB1.DBW2;
      L     DB1.DBW 2;
      T     HMI.Number;
END_FUNCTION_BLOCK
""",
            symbols_text=symbols,
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 1)

    def test_validate_accepts_symbolic_db_with_absolute_offset(self) -> None:
        symbols = '"FB_SORTER                ","FB      1   ","FB      1 ","GEN:                                                                            "\r\n'
        root = self._write_workspace(
            str(self.test_root),
            "fb_export.awl",
            """FUNCTION_BLOCK FB 1
TITLE =%version: 0.1 % CN: 30
FAMILY : PROCESS
NAME : SORTER
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      L     HMI.DBW2;
END_FUNCTION_BLOCK
""",
            symbols_text=symbols,
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 1)

    def test_validate_accepts_absolute_db_with_symbolic_field(self) -> None:
        symbols = '"FB_SORTER                ","FB      1   ","FB      1 ","GEN:                                                                            "\r\n'
        root = self._write_workspace(
            str(self.test_root),
            "fb_export.awl",
            """FUNCTION_BLOCK FB 1
TITLE =%version: 0.1 % CN: 30
FAMILY : PROCESS
NAME : SORTER
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      L     DB1.Number;
END_FUNCTION_BLOCK
""",
            symbols_text=symbols,
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 1)

    def test_validate_accepts_absolute_pointer_literals(self) -> None:
        symbols = '"FB_SORTER                ","FB      1   ","FB      1 ","GEN:                                                                            "\r\n'
        root = self._write_workspace(
            str(self.test_root),
            "fb_export.awl",
            """FUNCTION_BLOCK FB 1
TITLE =%version: 0.1 % CN: 30
FAMILY : PROCESS
NAME : SORTER
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      CALL  "BLKMOV"
       SRCBLK :=P#DB1.DBX0.0 WORD 1
       DSTBLK :=P#I1000.0 BYTE 12
      PVAL   :=P#P 0.0;
      L     DBW [AR1,P#0.0];
      L     P##s_Msg_Statistical;
      L     P#DBX 0.0;
END_FUNCTION_BLOCK
""",
            symbols_text=symbols,
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 1)

    def test_validate_rejects_symbolic_pointer_target(self) -> None:
        symbols = '"FB_SORTER                ","FB      1   ","FB      1 ","GEN:                                                                            "\r\n'
        root = self._write_workspace(
            str(self.test_root),
            "fb_export.awl",
            """FUNCTION_BLOCK FB 1
TITLE =%version: 0.1 % CN: 30
FAMILY : PROCESS
NAME : SORTER
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      CALL  "BLKMOV"
       SRCBLK :=P#HMI.DBW2 WORD 1;
END_FUNCTION_BLOCK
""",
            symbols_text=symbols,
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"HMI\.DBW2"):
            validate_workspace(paths)

    def test_validate_rejects_mixed_pointer_target(self) -> None:
        symbols = '"FB_SORTER                ","FB      1   ","FB      1 ","GEN:                                                                            "\r\n'
        root = self._write_workspace(
            str(self.test_root),
            "fb_export.awl",
            """FUNCTION_BLOCK FB 1
TITLE =%version: 0.1 % CN: 30
FAMILY : PROCESS
NAME : SORTER
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      CALL  "BLKMOV"
       SRCBLK :=P#DB1.Number WORD 1
END_FUNCTION_BLOCK
""",
            symbols_text=symbols,
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"DB1\.Number"):
            validate_workspace(paths)

    def test_validate_accepts_block_calls_and_jumps(self) -> None:
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", STL_VALIDATE_MONOLITH, symbols_text="\r\n")
        paths = resolve_workspace(root)
        count = split_exported_workspace(paths)
        self.assertEqual(count, 4)
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 4)

    def test_validate_accepts_sfc_call_target(self) -> None:
        monolith = """FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      CALL SFC   46 ;
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 1)

    def test_validate_accepts_quoted_local_instance_calls(self) -> None:
        symbols = '"FB_MAIN                  ","FB      1   ","FB      1 ","GEN:                                                                            "\r\n'
        root = self._write_workspace(
            str(self.test_root),
            "quoted_instance.awl",
            QUOTED_INSTANCE_MONOLITH,
            symbols_text=symbols,
        )
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 1)

    def test_validate_rejects_missing_jump_label(self) -> None:
        monolith = STL_VALIDATE_MONOLITH.replace("JU    DA01;", "JU    ZZ99;")
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"ZZ99"):
            validate_workspace(paths)

    def test_validate_rejects_fb_call_without_instance_db(self) -> None:
        monolith = STL_VALIDATE_MONOLITH.replace("CALL FB 100 , DB 100 (", "CALL FB 100 (")
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"instance DB"):
            validate_workspace(paths)

    def test_validate_rejects_unknown_local_instance_call(self) -> None:
        monolith = STL_VALIDATE_MONOLITH.replace("CALL #s_Helper (", "CALL #s_Missing (")
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"not declared"):
            validate_workspace(paths)

    def test_validate_accepts_quoted_target_and_instance_blocks(self) -> None:
        monolith = """FUNCTION_BLOCK FB 2
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Value : INT;
END_VAR
VAR_OUTPUT
  o_Value : INT;
END_VAR
BEGIN
END_FUNCTION_BLOCK

DATA_BLOCK DB 2
TITLE =
NAME : HELPER_DATA
VERSION : 0.1
BEGIN
END_DATA_BLOCK

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
VAR_TEMP
  t_Value : INT;
END_VAR
BEGIN
NETWORK
TITLE =
      CALL "HELPER" , "HELPER_DATA" (
           i_Value := #t_Value);
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validate_workspace(paths)

    def test_validate_rejects_call_parameter_type_mismatch(self) -> None:
        monolith = STL_VALIDATE_MONOLITH.replace("  t_Value : INT;", "  t_Value : DINT;")
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"expects INT but got DINT"):
            validate_workspace(paths)

    def test_validate_accepts_call_omitting_optional_outputs(self) -> None:
        monolith = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Value : INT;
END_VAR
VAR_OUTPUT
  o_Value : INT;
END_VAR
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
VAR_TEMP
  t_Value : INT;
END_VAR
BEGIN
NETWORK
TITLE =
      CALL FC 100 (
           i_Value := #t_Value);
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validate_workspace(paths)

    def test_validate_accepts_any_and_block_db_call_arguments(self) -> None:
        monolith = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Any : ANY;
  i_Ptr : POINTER;
  i_TableDB : BLOCK_DB;
END_VAR
BEGIN
END_FUNCTION

DATA_BLOCK DB 2
TITLE =
NAME : HELPER_DATA
VERSION : 0.1
BEGIN
END_DATA_BLOCK

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
VAR_TEMP
  t_Any : ANY;
END_VAR
BEGIN
NETWORK
TITLE =
      CALL FC 100 (
           i_Any := P#DBX 0.0 BYTE 10,
           i_Ptr := #t_Any,
           i_TableDB := "HELPER_DATA");
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validate_workspace(paths)

    def test_validate_accepts_bare_db_reference_for_block_db_call(self) -> None:
        monolith = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_TableDB : BLOCK_DB;
END_VAR
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      CALL FC 100 (
           i_TableDB := DB 2);
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validate_workspace(paths)

    def test_validate_rejects_numeric_argument_for_any_call(self) -> None:
        monolith = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Any : ANY;
END_VAR
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
VAR_TEMP
  t_Any : ANY;
END_VAR
BEGIN
NETWORK
TITLE =
      CALL FC 100 (
           i_Any := 1);
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"expects ANY but got numeric"):
            validate_workspace(paths)

    def test_validate_rejects_malformed_pointer_argument_in_call(self) -> None:
        monolith = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Any : ANY;
END_VAR
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      CALL FC 100 (
           i_Any := P#DBX 0.0
             WORD 10
             EXTRA);
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"invalid pointer literal"):
            validate_workspace(paths)

    def test_validate_accepts_db_address_arguments_for_any_call(self) -> None:
        monolith = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Any : ANY;
  i_Any2 : ANY;
END_VAR
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      CALL FC 100 (
           i_Any := DB1.DBX0.0,
           i_Any2 := DB1.Number);
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validated = validate_workspace(paths)
        self.assertEqual(len(validated), 2)

    def test_validate_accepts_complex_local_variable_for_any_call(self) -> None:
        monolith = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Any : ANY;
END_VAR
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
VAR
  s_Array : ARRAY [0 .. 1] OF INT;
END_VAR
BEGIN
NETWORK
TITLE =
      CALL FC 100 (
           i_Any := #s_Array);
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validate_workspace(paths)

    def test_validate_rejects_duplicate_declarations(self) -> None:
        monolith = STL_VALIDATE_MONOLITH.replace(
            "  t_Value : INT;\nEND_VAR",
            "  t_Value : INT;\n  t_Value : DINT;\nEND_VAR",
        )
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"Duplicate declaration detected: t_Value"):
            validate_workspace(paths)

    def test_validate_reports_multiple_errors(self) -> None:
        monolith = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Value : INT;
END_VAR
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
VAR_TEMP
  t_Value : DINT;
END_VAR
BEGIN
NETWORK
TITLE =
      CALL FC 100 (
           i_Value := #t_Value);
NETWORK
TITLE =
      CALL FC 100 (
           i_Unknown := #t_Value);
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaises(ParseError) as ctx:
            validate_workspace(paths)
        message = str(ctx.exception)
        self.assertIn("expects INT but got DINT", message)
        self.assertIn("unknown CALL parameter", message)

    def test_call_graph_report_marks_unreachable_blocks(self) -> None:
        monolith = """FUNCTION FC 2 : VOID
TITLE =
VERSION : 0.1
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 1
TITLE =
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      CALL FC 2 ();
END_FUNCTION_BLOCK

FUNCTION_BLOCK FB 99
TITLE =
VERSION : 0.1
BEGIN
END_FUNCTION_BLOCK

DATA_BLOCK DB 1
TITLE =
VERSION : 0.1
BEGIN
END_DATA_BLOCK

ORGANIZATION_BLOCK OB 1
TITLE =
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      CALL FB 1 , DB 1 ();
END_ORGANIZATION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "call_graph.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        parsed = validate_workspace(paths)

        graph = build_call_graph(parsed)
        self.assertIn(("FB", 99), graph.unreachable)
        report_path = default_call_graph_report_path(paths)
        write_call_graph_report(graph, paths.root, report_path)
        report_text = report_path.read_text(encoding="utf-8")
        self.assertIn("Call Graph", report_text)
        self.assertIn("Call tree from selected block", report_text)
        self.assertIn("Selected Block", report_text)
        self.assertIn("Unreachable Blocks", report_text)
        self.assertIn("search-status", report_text)
        self.assertIn("exactSearchMatch", report_text)
        self.assertIn("Focus block", report_text)
        self.assertIn("FB 99", report_text)

    def test_validate_rejects_missing_operand_in_boolean_instruction(self) -> None:
        monolith = """FUNCTION_BLOCK FB 1
TITLE =
VERSION : 0.1
VAR_INPUT
  i_Value : BOOL;
END_VAR
BEGIN
NETWORK
TITLE =
      A    ;
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"requires an operand"):
            validate_workspace(paths)

    def test_validate_accepts_bool_operand_in_boolean_instruction(self) -> None:
        monolith = """FUNCTION_BLOCK FB 1
TITLE =
VERSION : 0.1
VAR_INPUT
  i_Value : BOOL;
END_VAR
BEGIN
NETWORK
TITLE =
      A     #i_Value;
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validate_workspace(paths)

    def test_validate_accepts_or_without_operand(self) -> None:
        monolith = """FUNCTION_BLOCK FB 1
TITLE =
VERSION : 0.1
VAR_INPUT
  i_Value : BOOL;
END_VAR
BEGIN
NETWORK
TITLE =
      O    ;
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        validate_workspace(paths)

    def test_validate_rejects_missing_statement_semicolon(self) -> None:
        monolith = """FUNCTION_BLOCK FB 1
TITLE =
VERSION : 0.1
VAR_INPUT
  i_Value : BOOL;
END_VAR
BEGIN
NETWORK
TITLE =
      A     #i_Value
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"missing ';' at end of statement"):
            validate_workspace(paths)

    def test_validate_rejects_missing_call_semicolon(self) -> None:
        monolith = """FUNCTION FC 100 : VOID
TITLE =
NAME : HELPER
VERSION : 0.1
VAR_INPUT
  i_Value : INT ;
END_VAR
BEGIN
END_FUNCTION

FUNCTION_BLOCK FB 1
TITLE =
NAME : MAIN
VERSION : 0.1
VAR_TEMP
  t_Value : INT;
END_VAR
BEGIN
NETWORK
TITLE =
      CALL FC 100 (
           i_Value := #t_Value)
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"missing ';' at end of CALL statement"):
            validate_workspace(paths)

    def test_validate_rejects_numeric_operand_in_boolean_instruction(self) -> None:
        monolith = """FUNCTION_BLOCK FB 1
TITLE =
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      A     1;
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"bit-compatible operand"):
            validate_workspace(paths)

    def test_validate_rejects_bit_operand_in_transfer_instruction(self) -> None:
        monolith = """FUNCTION_BLOCK FB 1
TITLE =
VERSION : 0.1
BEGIN
NETWORK
TITLE =
      L     DBX 0.0;
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"does not accept a bit operand"):
            validate_workspace(paths)

    def test_validate_rejects_extra_operand_in_set_instruction(self) -> None:
        monolith = """FUNCTION_BLOCK FB 1
TITLE =
VERSION : 0.1
VAR_INPUT
  i_Value : BOOL;
END_VAR
BEGIN
NETWORK
TITLE =
      SET   1;
END_FUNCTION_BLOCK
"""
        root = self._write_workspace(str(self.test_root), "stl_validate.awl", monolith, symbols_text="\r\n")
        paths = resolve_workspace(root)
        split_exported_workspace(paths)
        with self.assertRaisesRegex(ParseError, r"does not take an operand"):
            validate_workspace(paths)


if __name__ == "__main__":
    unittest.main()
