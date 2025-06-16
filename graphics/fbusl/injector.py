from FreeBodyEngine.graphics.fbusl.ast_nodes import *

class Injector:
    """
    Injects FBE material functionality into the shader.
    """
    def __init__(self, tree):
        self.tree: Tree = tree
        self.main_name = None
        self.new = Tree()
        
    def inject(self):
        self.overide_main()
        self.inject_main()

    def overide_main(self):
        # overide main function
        funcs = []
        main_calls: list[FuncCall] = []
        main = None

        for node in self.tree:
            if isinstance(node, FuncDecl):
                if node.name == "main":
                    main = node
                funcs.append(node.name)
            if isinstance(node, FuncCall):
                if node.name == "main":
                    main_calls.append(node)

        if main == None:
            raise SyntaxError("No main function defined.")
        else:
            i = 0
            new_name = f"user_main{i}"
            
            while new_name in funcs:
                i += 1
                new_name = f'user_main{i}'
            
            main.name = new_name

            for call in main_calls:
                call.name = new_name
            
            self.main_name = new_name
        
    def inject_main(self):
        pass