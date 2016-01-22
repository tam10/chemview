"""GGplot like interface"""
import uuid

import matplotlib as mpl
import matplotlib.cm as cm
import numpy as np
from IPython.display import Image, display

from .utils import get_atom_color
from .widget import RepresentationViewer, TrajectoryControls


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

    def copy(self):
        return type(self)(self)

class Aes(AttrDict):
    
    def __init__(self, *args, **kwargs):
        super(Aes, self).__init__(*args, **kwargs)

    def __repr__(self):
        return str(self.copy())

    def updated(self, other):
        copy = self.copy()
        copy.update(other)
        return copy

class ggview(object):
    def __init__(self, aes):
        self.aes = aes
        self.geometries = []
        self.scales = []

    def display(self):
        # Generate primitives
        aes = self.aes
        
        # Apply scale that map data to aes
        for scale in self.scales:
            scale.render()
            aes = scale.apply(aes)
        
        primitives = []
        for geometry in self.geometries:
            primitives.extend(geometry.produce(aes))

        # We generate a json description
        rv = RepresentationViewer.from_scene({"representations" : primitives})
        return rv

    def __add__(self, other):
        
        if isinstance(other, Geom):
            self.geometries.append(other)
            
        elif isinstance(other, Scale):
            self.scales.append(other)
        else:
            raise ValueError("Data type not understood {}".format(type(other)))

        return self


class ggtraj(ggview):
    
    def __init__(self, frames, aes):
        frame_aes = ggtraj._make_frame_aes(aes, 0)
        super(ggtraj, self).__init__(frame_aes)
        self.frames = frames
        self.traj_aes = aes
        self.update_funcs = []

    def display(self):
        # Generate primitives
        aes = self.aes
        # Apply scale that map data to aes
        for scale in self.scales:
            scale.render()
            aes = scale.apply(aes)
        
        primitives = []
        for geometry in self.geometries:
            prims = geometry.produce(aes)
            primitives.extend(prims)
            
            self.update_funcs.append((prims[0]["rep_id"], geometry.update))
        
        rv = RepresentationViewer.from_scene({"representations" : primitives})        
        tc = TrajectoryControls(self.frames)
        tc.on_frame_change(lambda frame, self=self, widget=rv: self.update(widget, frame))
        # Add trajectory viewer too
        display(rv)
        display(tc)
        
        
        return tc, rv

    @staticmethod
    def _make_frame_aes(aes, frame):
        frame_aes = Aes()
        
        # Make a copy
        for k in aes.keys():
            frame_aes[k] = aes[k]
        
        # Override the traj ones
        for k in aes.keys():
            if k.endswith("_traj"):
                frame_aes[k[:-5]] = aes[k][frame]

        return frame_aes
        
    def update(self, widget, frame):
        
        for rep_id, func in self.update_funcs:
            aes = ggtraj._make_frame_aes(self.traj_aes, frame)
            for scale in self.scales:
                aes = scale.apply(aes)
            
            options = func(aes)
            widget.update_representation(rep_id, options)
    


class Geom(object):
    """Base class for all geometric objects"""
    
    def __init__(self, aes=Aes()):
        self.aes = aes
    
    def produce(self, aes):
        raise NotImplementedError()

    def update(self, aes):
        raise NotImplementedError()

class GeomPoints(Geom):

    def produce(self, aes):
        # If an aes was passed, we override...
        aes = aes.updated(self.aes)

        # Return a dict of primitives produced from aes data
        return [{
                "rep_id" : uuid.uuid1().hex,
                'rep_type': "points",
                "options": { "coordinates": aes.xyz,
                             "colors": process_colors(len(aes.xyz), aes.get("colors", None)),
                             "sizes": process_sizes(len(aes.xyz), aes.get("sizes", 1)),
                             "visible": aes.get("visible", None) }
                }]

    def update(self, aes):
        # we return options
        return { "coordinates": aes.xyz,
                 "colors": process_colors(len(aes.xyz), aes.get("colors", None)),
                 "sizes": process_sizes(len(aes.xyz), aes.get("sizes", None)),
                 "visible": aes.get("visible", None) }


class GeomSpheres(Geom):

    def produce(self, aes):
        # If an aes was passed, we override...
        aes = aes.updated(self.aes)

        # Return a dict of primitives produced from aes data
        return [{
                "rep_id" : uuid.uuid1().hex,
                'rep_type': "spheres",
                "options": { "coordinates": aes.xyz,
                             "colors": process_colors(len(aes.xyz), aes.get("colors", None)),
                             "radii": process_sizes(len(aes.xyz), aes.get("sizes", 1)),
                             "visible": aes.get("visible", None) }
                }]



class GeomLines(Geom):

    def produce(self, aes):
        # Return a dict of primitives produced from aes data
        aes = aes.updated(self.aes)
        
        xyz = np.array(aes.xyz)
        edges = np.array(aes.edges, 'uint8')
        colors = process_colors(len(xyz), aes.get("colors", None))
        return [{ "rep_id" : uuid.uuid1().hex,
                  'rep_type': "lines",
                  "options" : {
                      "startCoords": np.take(xyz, edges[:, 0], axis=0),
                      "endCoords": np.take(xyz, edges[:, 1], axis=0),
                      "startColors": colors,
                      "endColors": colors}
                 }]

class GeomCylinders(Geom):

    def produce(self, aes):
        # Return a dict of primitives produced from aes data
        aes = aes.updated(self.aes)
        
        xyz = np.array(aes.xyz)
        edges = np.array(aes.edges, 'uint8')
        colors = process_colors(len(xyz), aes.get("colors", None))
        return [{ "rep_id" : uuid.uuid1().hex,
                  'rep_type': "cylinders",
                  "options" : {
                      "startCoords": np.take(xyz, edges[:, 0], axis=0),
                      "endCoords": np.take(xyz, edges[:, 1], axis=0),
                      "colors": colors,
                      "radii": process_sizes(len(aes.xyz), aes.get("sizes", None))}
                 }]

class GeomSurface(Geom):
    
    def produce(self, aes):
        pass

from numpy.lib.stride_tricks import as_strided

def pairs(a):
    """Return array of pairs of adjacent elements in a.

    >>> pairs([1, 2, 3, 4])
    array([[1, 2],
           [2, 3],
           [3, 4]])

    """
    a = np.asarray(a)
    return as_strided(a, shape=(a.size - 1, 2), strides=a.strides * 2)

def groupby_ix(a):
    p = pairs(a)
    diff_ix = np.nonzero(p[:, 0] != p[:, 1])[0]
    starts_ix = np.append(np.insert(diff_ix + 1, 0, 0), a.shape[0])
    
    return pairs(starts_ix)

class GeomProteinCartoon(Geom):
    
    def __init__(self, aes):
        super(GeomProteinCartoon, self).__init__(aes)
        
        # It is necessary to have
        # aes.xyz (Coordinates)
        # aes.types (Atom types)
        # aes.secondary (secondary structure)
        
    
    def produce(self, aes):
        aes = aes.updated(self.aes)
        
        primitives = []
        
        for xyz, normals in zip(*self._extract_helix_coords_normals(aes)):
            g_helices = GeomRibbon(Aes(xyz=xyz, normals=normals), color=0xff0000)
            primitives.extend(g_helices.produce(Aes()))
        
        for xyz, normals in zip(*self._extract_sheet_coords_normals(aes)):
            g_sheets = GeomRibbon(Aes(xyz=xyz, normals=normals, resolution=16), 
                                  arrow=True, color=0x00ffff)
            primitives.extend(g_sheets.produce(Aes()))

        for xyz in self._extract_coil_coords(aes):
            g_coils = GeomLines(Aes(xyz=xyz, edges=pairs(range(len(xyz)))))
            primitives.extend(g_coils.produce(Aes()))
        
        return primitives
    
    def _extract_helix_coords_normals(self, aes):
        # First, extract the helices from the secondary
        groups_ix = groupby_ix(aes.secondary_id)
        helices_ix = groups_ix[aes.secondary_type[groups_ix[:, 0]] == 'H']
        
        backbone_list = [aes.xyz[aes.types == 'CA'][i:j] for i, j in helices_ix] 
        normals_list = [alpha_helix_normals(backbone) for backbone in backbone_list]
        
        return backbone_list, normals_list

    def _extract_sheet_coords_normals(self, aes):
        groups_ix = groupby_ix(aes.secondary_id)
        sheets_ix = groups_ix[aes.secondary_type[groups_ix[:, 0]] == 'S']
        
        ca_list = [aes.xyz[aes.types == 'CA'][i:j] for i, j in sheets_ix] 
        c_list = [aes.xyz[aes.types == 'C'][i:j] for i, j in sheets_ix] 
        o_list = [aes.xyz[aes.types == 'O'][i:j] for i, j in sheets_ix] 
        
        normals_list = [beta_sheet_normals(ca, c, o) for ca, c, o in zip(ca_list, c_list, o_list)]
        
        return ca_list, normals_list

    def _extract_coil_coords(self, aes):
        groups_ix = groupby_ix(aes.secondary_id)
        coils_ix = groups_ix[aes.secondary_type[groups_ix[:, 0]] == 'C']
        
        # We remove id = 0 because they are heteroatoms
        coils_id = aes.secondary_id[coils_ix[:, 0]]
        coils_ix = coils_ix[coils_id != 0, :]
        
        coils_ix[:, 1] += 1
        coils_ix[:, 0] -= 1
        coils_ix[coils_ix > len(aes.secondary_type)] = len(aes.secondary_type)
        coils_ix[coils_ix < 0] = 0
        
        backbone_list = [aes.xyz[aes.types == 'CA'][i:j] for i, j in coils_ix]
        return backbone_list

from chemview.utils import normalized, beta_sheet_normals

def alpha_helix_normals(ca):
    K_AVG = 5
    K_OFFSET = 2
    
    if len(ca) <= K_AVG:
        start = ca[0]
        end = ca[-1]
        helix_dir = normalized(end - start)
        
        position = ca - start
        projected_pos = np.array([np.dot(r, helix_dir) * helix_dir for r in position]) 
        normals = normalized(position - projected_pos)
        return [start] * len(normals), [end] * len(normals), normals
    
    # Start and end point for normals
    starts = []
    ends = []
    

    for i in range(len(ca) - K_AVG):
        starts.append(ca[i:i + K_AVG - K_OFFSET].mean(axis=0))
        ends.append(ca[i+K_OFFSET:i + K_AVG].mean(axis=0))
        
    starts = np.array(starts)
    ends = np.array(ends)
    
    # position relative to "start point"
    normals = []
    for i,r in enumerate(ca):
        k = i if i < len(ca) - K_AVG else -1
        position = r - starts[k]
        # Find direction of the helix
        helix_dir = normalized(ends[k] - starts[k])
        # Project positions on the helix
        
        projected_pos = np.dot(position, helix_dir) * helix_dir        
        normals.append(normalized(position - projected_pos))


    return np.array(normals)

class GeomRibbon(Geom):
    
    def __init__(self, aes, color=0xffffff, width=0.2, arrow=False):
        super(GeomRibbon, self).__init__(aes)
        self.color = color
        self.width = width
        self.arrow = arrow
    
    def produce(self, aes):
        aes = aes.updated(self.aes)
        
        xyz = np.array(aes.xyz)
        normals = np.array(aes.normals)
        
        return [{'rep_id': uuid.uuid1().hex,
                 'rep_type': 'ribbon',
                 'options': {
                    'coordinates': xyz,
                    'normals': normals,
                    'resolution': aes.get("resolution", 4),
                    'color': self.color,
                    'width': self.width,
                    'arrow': self.arrow
                 }}]

class Scale(object):
    pass

class ScaleColorsGradient(Scale):
    property = "colors"
    
    def __init__(self, limits=None,  palette="YlGnBu"):
        self.limits = limits
        self.palette = palette
    
    def apply(self, aes):
        aes = aes.copy()
        colors = process_colors(len(aes.xyz), aes.get("colors", None), self.limits, self.palette)
        aes.colors = colors
        return aes
    
    def render(self):
        from matplotlib import pyplot
        import matplotlib as mpl
        
        # Make a figure and axes with dimensions as desired.
        fig = pyplot.figure(figsize=(8, 3))
        ax1 = fig.add_axes([0.05, 0.80, 0.9, 0.15])

        # Set the colormap and norm to correspond to the data for which
        # the colorbar will be used.
        cmap = mpl.cm.get_cmap(self.palette)
        norm = mpl.colors.Normalize(vmin=self.limits[0], vmax=self.limits[1])

        # ColorbarBase derives from ScalarMappable and puts a colorbar
        # in a specified axes, so it has everything needed for a
        # standalone colorbar.  There are many more kwargs, but the
        # following gives a basic continuous colorbar with ticks
        # and labels.
        cb1 = mpl.colorbar.ColorbarBase(ax1, cmap=cmap,
                                        norm=norm,
                                        orientation='horizontal')
        #cb1.set_label('Some Units')
        from IPython.display import display
        from six import BytesIO
        data = BytesIO()
        fig.savefig(data, format="png")
        display(Image(data=data.getvalue()))


def rgbint_to_hex(rgb):
    return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]

def process_colors(size, colors, limits=None, palette="YlGnBu"):
    if colors is None:
        return [0xffffff] * size
    
    elif isinstance(colors, list) and len(colors) == 0:
        return [0xffffff] * size
    
    elif isinstance(colors, list) and isinstance(colors[0], (str, bytes)):
        return [get_atom_color(c) for c in colors]
    
    elif isinstance(colors, list) and isinstance(colors[0], (int, np.int32, np.int64, np.int16)):
        # We cast to 32 bit
        return [int(c) for c in colors]
    
    elif isinstance(colors, np.ndarray):
        return process_colors(size, colors.tolist(), limits, palette)
    
    elif isinstance(colors, list) and isinstance(colors[0], (float, np.float32, np.float64)):
        if limits is None:
             vmin = min(colors)
             vmax = max(colors)
        else:
            vmin, vmax = limits
        
        norm = mpl.colors.Normalize(vmin=vmin, vmax=vmax)
        cmap = cm.get_cmap(palette)
        m = cm.ScalarMappable(norm=norm, cmap=cmap)
        return [rgbint_to_hex(c) for c in m.to_rgba(colors, bytes=True)[:, :3]]
    else:
        raise ValueError("Wrong color format : {}".format(type(colors)))

def process_sizes(size, sizes):
    if sizes is None:
        return [1.0] * size
    if isinstance(sizes, int):
        return [sizes] * size
    elif isinstance(sizes, list) and len(sizes) == 0:
        return [1.0] * size
    elif isinstance(sizes, list) and isinstance(sizes[0], (int, float)):
        return sizes
    else:
        raise ValueError("Wrong sizes format")
