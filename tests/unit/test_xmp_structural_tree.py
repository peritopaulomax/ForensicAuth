"""Testes da árvore estrutural XMP com elementos aninhados."""

import xml.etree.ElementTree as ET

from core.metadata.xmp_packet import _build_structural_node, _parse_xmp_packet

SAMPLE_NESTED_XMP = b"""<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/'>
  <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'
           xmlns:xmp='http://ns.adobe.com/xap/1.0/'
           xmlns:exif='http://ns.adobe.com/exif/1.0/'>
    <rdf:Description rdf:about=''
      xmp:CreatorTool='Adobe Photoshop'
      xmp:CreateDate='2012-05-15T11:25:05-03:00'>
      <exif:ComponentsConfiguration>
        <rdf:Seq>
          <rdf:li>1</rdf:li>
          <rdf:li>2</rdf:li>
        </rdf:Seq>
      </exif:ComponentsConfiguration>
      <exif:Flash rdf:parseType='Resource'>
        <exif:Fired>False</exif:Fired>
        <exif:Return>2</exif:Return>
      </exif:Flash>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end='w'?>"""


def _find_child(node: dict, name: str) -> dict | None:
    for child in node.get("children", []):
        if child.get("name") == name and child.get("node_type") != "property":
            return child
    return None


class TestXmpStructuralTree:
    def test_description_attributes_become_property_nodes(self):
        root = ET.fromstring(SAMPLE_NESTED_XMP)
        tree = _build_structural_node(root, "0")
        desc = _find_child(_find_child(tree, "RDF"), "Description")
        assert desc is not None
        props = [c for c in desc["children"] if c["node_type"] == "property"]
        assert len(props) >= 2
        assert any(c["name"] == "CreatorTool" for c in props)

    def test_nested_seq_and_flash_as_element_children(self):
        parsed = _parse_xmp_packet(SAMPLE_NESTED_XMP)
        desc = _find_child(_find_child(parsed["structural_tree"], "RDF"), "Description")
        assert desc is not None

        comp = _find_child(desc, "ComponentsConfiguration")
        assert comp is not None
        seq = _find_child(comp, "Seq")
        assert seq is not None
        assert seq["node_type"] == "container"
        li_nodes = [c for c in seq["children"] if c["name"] == "li"]
        assert len(li_nodes) == 2

        flash = _find_child(desc, "Flash")
        assert flash is not None
        fired = _find_child(flash, "Fired")
        ret = _find_child(flash, "Return")
        assert fired is not None and fired.get("value") == "False"
        assert ret is not None and ret.get("value") == "2"

    def test_description_rdf_attributes_expanded_as_properties(self):
        attr_xmp = b"""<x:xmpmeta xmlns:x='adobe:ns:meta/'>
  <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'
           xmlns:xmp='http://ns.adobe.com/xap/1.0/'
           xmlns:tiff='http://ns.adobe.com/tiff/1.0/'>
    <rdf:Description rdf:about=''
      xmp:CreatorTool='Ver.1.00'
      xmp:CreateDate='2012-05-15T11:25:05-03:00'
      tiff:Make='NIKON CORPORATION'
      tiff:Model='NIKON D70s'/>
  </rdf:RDF>
</x:xmpmeta>"""
        parsed = _parse_xmp_packet(attr_xmp)
        desc = _find_child(_find_child(parsed["structural_tree"], "RDF"), "Description")
        props = [c for c in desc["children"] if c["node_type"] == "property"]
        names = {c["name"] for c in props}
        assert "CreatorTool" in names
        assert "Make" in names
        assert "Model" in names
        assert len(props) >= 4

    def test_property_nodes_include_forensic_hints(self):
        parsed = _parse_xmp_packet(SAMPLE_NESTED_XMP)
        desc = _find_child(_find_child(parsed["structural_tree"], "RDF"), "Description")
        props = {c["name"]: c for c in desc["children"] if c["node_type"] == "property"}
        assert props["CreatorTool"]["hint"]
        assert "criou" in props["CreatorTool"]["hint"].lower()

        flash = _find_child(desc, "Flash")
        fired = _find_child(flash, "Fired")
        ret = _find_child(flash, "Return")
        assert fired["hint"] and "flash" in fired["hint"].lower()
        assert ret["hint"]

        li = _find_child(_find_child(_find_child(desc, "ComponentsConfiguration"), "Seq"), "li")
        assert li["hint"] and "Seq" in li["hint"] or "item" in li["hint"].lower()

    def test_semantic_groups_include_hints_for_nested_and_flat_properties(self):
        parsed = _parse_xmp_packet(SAMPLE_NESTED_XMP)
        props = {p["name"]: p for g in parsed["semantic_groups"] for p in g["properties"]}
        assert any(p.get("hint") for p in props.values())
        creator = next(p for n, p in props.items() if "CreatorTool" in n)
        assert creator["hint"]
        fired = next(p for n, p in props.items() if n.endswith("Fired") or ".Fired" in n or n == "Fired")
        assert fired["hint"]


SAMPLE_HISTORY_XMP = b"""<x:xmpmeta xmlns:x='adobe:ns:meta/'>
  <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'
           xmlns:xmpMM='http://ns.adobe.com/xap/1.0/mm/'
           xmlns:stEvt='http://ns.adobe.com/xap/1.0/sType/ResourceEvent#'>
    <rdf:Description rdf:about=''>
      <xmpMM:History>
        <rdf:Seq>
          <rdf:li>
            <rdf:Description
              stEvt:action='created'
              stEvt:instanceID='xmp.iid:ABC'
              stEvt:softwareAgent='Adobe Photoshop CS4 Windows'
              stEvt:when='2012-05-15T12:31:40-03:00'/>
          </rdf:li>
        </rdf:Seq>
      </xmpMM:History>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>"""


class TestXmpHistoryHints:
    def test_history_resource_event_properties_have_hints(self):
        parsed = _parse_xmp_packet(SAMPLE_HISTORY_XMP)
        props = {p["name"]: p for g in parsed["semantic_groups"] for p in g["properties"]}
        action = next(p for n, p in props.items() if n.endswith("action"))
        assert "ação" in action["hint"].lower() or "acao" in action["hint"].lower()
        agent = next(p for n, p in props.items() if "softwareAgent" in n)
        assert agent["hint"]
        when = next(p for n, p in props.items() if n.endswith("when"))
        assert when["hint"]
