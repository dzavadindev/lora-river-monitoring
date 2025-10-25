function time_format(ascii) {
  if (ascii.length != 14) {
    return null;
  }
  
  const dd = ascii.slice(0,2);
  const MM = ascii.slice(2,4);
  const yyyy = ascii.slice(4,8);
  const hh = ascii.slice(8,10);
  const mm = ascii.slice(10,12);
  const ss = ascii.slice(12);

  return `${yyyy}-${MM}-${dd}T${hh}:${mm}:${ss}Z`;
}

function decodeUplink(input) {
  const bytes = input.bytes;

  const flow  = bytes[0];
  const level = bytes[1];
  const temp  = (bytes[2] << 24) >> 24; // buffer has temp as u8, interpret as signed i8
 
  const time = time_format(String.fromCharCode(...bytes.slice(3, 17)));
 
  const ascii = String.fromCharCode(...bytes.slice(17)); // everything after third byte
  const [latStr, lonStr] = ascii.split(','); // to get lat and long 

  const lat = parseFloat(latStr);
  const lon = parseFloat(lonStr);

  return {
    data: {
      flow_deg: flow,
      water_level_mm: level,
      water_temp_c: temp,
      latitude: lat,
      longitude: lon,
      timestamp: time
    }
  };
}
