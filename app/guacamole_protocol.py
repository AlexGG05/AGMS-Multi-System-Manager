"""Bounded Guacamole handshake. Browser never receives RDP credentials."""
import asyncio

MAX_ELEMENT = 1024 * 1024

def instruction(*args):
    return (','.join(str(len(str(arg)))+'.'+str(arg) for arg in args)+';').encode('utf-8')

async def read_instruction(reader):
    result=[];total=0
    while len(result)<256:
        size=await reader.readuntil(b'.')
        if len(size)>9 or not size[:-1].isdigit():raise ValueError('Invalid Guacamole length')
        count=int(size[:-1]);total+=count
        if total>MAX_ELEMENT:raise ValueError('Guacamole element too large')
        # Guacamole lengths count Unicode codepoints, not UTF-8 bytes.
        value=bytearray()
        for _ in range(count):
            first=await reader.readexactly(1);value.extend(first)
            width=1 if first[0]<128 else 2 if 194<=first[0]<224 else 3 if 224<=first[0]<240 else 4 if 240<=first[0]<245 else 0
            if not width:raise ValueError('Invalid UTF-8')
            if width>1:value.extend(await reader.readexactly(width-1))
        result.append(value.decode('utf-8'))
        end=await reader.readexactly(1)
        if end==b';':return result
        if end!=b',':raise ValueError('Invalid Guacamole separator')
    raise ValueError('Too many Guacamole arguments')

async def handshake(reader,writer,config,address,width,height):
    writer.write(instruction('select','rdp'));await writer.drain()
    args=await asyncio.wait_for(read_instruction(reader),10)
    if not args or args[0]!='args':raise ValueError('Guacamole handshake rejected')
    version=args[1] if len(args)>1 and args[1].startswith('VERSION_') else None
    names=args[2:] if version else args[1:]
    options={'hostname':address,'port':config['port'],'username':config['username'],
             'password':config.get('password',''),'domain':config.get('domain',''),
             'security':'nla','ignore-cert':'false','cert-fingerprints':('sha256:'+':'.join(config['fingerprint'][i:i+2] for i in range(0,64,2))) if config.get('fingerprint') else '','read-only':'false',
             'disable-copy':'true','disable-paste':'true','enable-drive':'false',
             'disable-upload':'true','disable-download':'true','disable-audio':'true',
             'resize-method':'display-update','color-depth':'24'}
    writer.write(instruction('size',width,height,96))
    writer.write(instruction('audio'));writer.write(instruction('video'))
    writer.write(instruction('image','image/png','image/jpeg'))
    values=[options.get(name,'') for name in names]
    writer.write(instruction('connect',*([version] if version else []),*values));await writer.drain()
    ready=await asyncio.wait_for(read_instruction(reader),20)
    if not ready or ready[0]!='ready':raise ValueError('RDP connection rejected')
    return ready[1]


class ClientParser:
    """Parse bounded browser instructions, including partial WebSocket frames."""
    def __init__(self):self.buffer=''
    def feed(self,text):
        self.buffer+=text
        if len(self.buffer)>65536:raise ValueError('Guacamole input too large')
        result=[]
        while self.buffer:
            pos=0;args=[]
            while True:
                dot=self.buffer.find('.',pos)
                if dot<0:
                    if len(self.buffer)-pos>8:raise ValueError('Invalid Guacamole length')
                    return result
                size=self.buffer[pos:dot]
                if not size.isascii() or not size.isdigit() or len(size)>8:raise ValueError('Invalid Guacamole length')
                end=dot+1+int(size)
                if end-dot>MAX_ELEMENT:raise ValueError('Guacamole element too large')
                if len(self.buffer)<=end:return result
                args.append(self.buffer[dot+1:end]);separator=self.buffer[end];pos=end+1
                if len(args)>256:raise ValueError('Too many Guacamole arguments')
                if separator==';':break
                if separator!=',':raise ValueError('Invalid Guacamole separator')
            result.append(args);self.buffer=self.buffer[pos:]
        return result


def client_instruction(args):
    """Only interactive input; bound dimensions before guacd can allocate displays."""
    def number(value,low,high):
        if not isinstance(value,str) or len(value)>16 or not value.isascii() or not (value[1:] if value.startswith('-') and low<0 else value).isdigit():raise ValueError('Invalid input number')
        result=int(value)
        if not low<=result<=high:raise ValueError('Input number outside bounds')
        return result
    if not args:raise ValueError('Empty input')
    opcode=args[0]
    if opcode=='' and len(args)==3 and args[1]=='ping':number(args[2],0,2**53-1)
    elif opcode=='key' and len(args)==3:
        number(args[1],0,0x1fffffff);number(args[2],0,1)
    elif opcode=='mouse' and len(args)==4:
        x=number(args[1],-32768,32767);y=number(args[2],-32768,32767);number(args[3],0,31)
        args=[opcode,str(max(0,x)),str(max(0,y)),args[3]]
    elif opcode=='size' and len(args) in (3,4):
        width=number(args[1],1,100000);height=number(args[2],1,100000)
        args=[opcode,str(max(320,min(3840,width))),str(max(240,min(2160,height)))]+args[3:]
        if len(args)==4:number(args[3],48,384)
    elif opcode=='sync' and len(args)==2:number(args[1],0,2**53-1)
    elif opcode=='ack' and len(args)==4:
        number(args[1],0,65535);number(args[3],0,65535)
        if len(args[2])>1024:raise ValueError('Ack message too large')
    elif opcode=='nop' and len(args)==1:pass
    else:raise ValueError('Unsupported Guacamole input')
    return args
